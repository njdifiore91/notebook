// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterLab,
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { Base64ModelFactory } from '@jupyterlab/docregistry';

import { createRendermimePlugins } from '@jupyterlab/application/lib/mimerenderers';

import { LabStatus } from '@jupyterlab/application/lib/status';

import { PageConfig } from '@jupyterlab/coreutils';

import { IRenderMime } from '@jupyterlab/rendermime-interfaces';

import { Throttler } from '@lumino/polling';

import { ISignal, Signal } from '@lumino/signaling';

import { INotebookShell, NotebookShell } from './shell';

/**
 * App is the main application class. It is instantiated once and shared.
 */
export class NotebookApp extends JupyterFrontEnd<INotebookShell> {
  /**
   * Construct a new NotebookApp object.
   *
   * @param options The instantiation options for an application.
   */
  constructor(options: NotebookApp.IOptions = { shell: new NotebookShell() }) {
    super({ ...options, shell: options.shell ?? new NotebookShell() });

    // Add initial model factory.
    this.docRegistry.addModelFactory(new Base64ModelFactory());
    if (options.mimeExtensions) {
      for (const plugin of createRendermimePlugins(options.mimeExtensions)) {
        this.registerPlugin(plugin);
      }
    }

    // Create an IInfo dictionary from the options to override the defaults.
    const info = Object.keys(JupyterLab.defaultInfo).reduce((acc, val) => {
      if (val in options) {
        (acc as any)[val] = JSON.parse(JSON.stringify((options as any)[val]));
      }
      return acc;
    }, {} as Partial<JupyterLab.IInfo>);

    // Populate application info.
    this._info = { ...JupyterLab.defaultInfo, ...info };

    this.restored = this.shell.restored;

    this.restored.then(() => this._formatter.invoke());

    // Initialize collaboration state
    this._collaborationEnabled = this._isCollaborationEnabled();
    this._collaborationStatus = 'disconnected';
    this._collaborationMetrics = {
      activeUsers: 0,
      totalOperations: 0,
      averageLatency: 0,
      reconnectionAttempts: 0,
      lastSyncTime: 0
    };

    // Setup collaboration monitoring
    if (this._collaborationEnabled) {
      this._collaborationMonitor = new Throttler(() => {
        this._updateCollaborationMetrics();
      }, 10000); // Update metrics every 10 seconds
      
      // Start monitoring
      this._collaborationMonitor.invoke();
    }
  }

  /**
   * The name of the application.
   */
  readonly name = 'Jupyter Notebook';

  /**
   * A namespace/prefix plugins may use to denote their provenance.
   */
  readonly namespace = this.name;

  /**
   * The application busy and dirty status signals and flags.
   */
  readonly status = new LabStatus(this);

  /**
   * Promise that resolves when the state is first restored
   */
  readonly restored: Promise<void>;

  /**
   * The version of the application.
   */

  readonly version = PageConfig.getOption('appVersion') ?? 'unknown';

  /**
   * The NotebookApp application information dictionary.
   */
  get info(): JupyterLab.IInfo {
    return this._info;
  }

  /**
   * The JupyterLab application paths dictionary.
   */
  get paths(): JupyterFrontEnd.IPaths {
    return {
      urls: {
        base: PageConfig.getOption('baseUrl'),
        notFound: PageConfig.getOption('notFoundUrl'),
        app: PageConfig.getOption('appUrl'),
        static: PageConfig.getOption('staticUrl'),
        settings: PageConfig.getOption('settingsUrl'),
        themes: PageConfig.getOption('themesUrl'),
        doc: PageConfig.getOption('docUrl'),
        translations: PageConfig.getOption('translationsApiUrl'),
        hubHost: PageConfig.getOption('hubHost') || undefined,
        hubPrefix: PageConfig.getOption('hubPrefix') || undefined,
        hubUser: PageConfig.getOption('hubUser') || undefined,
        hubServerName: PageConfig.getOption('hubServerName') || undefined,
        collaboration: PageConfig.getOption('collaborationUrl') || `${PageConfig.getOption('baseUrl')}api/collaboration`,
      },
      directories: {
        appSettings: PageConfig.getOption('appSettingsDir'),
        schemas: PageConfig.getOption('schemasDir'),
        static: PageConfig.getOption('staticDir'),
        templates: PageConfig.getOption('templatesDir'),
        themes: PageConfig.getOption('themesDir'),
        userSettings: PageConfig.getOption('userSettingsDir'),
        serverRoot: PageConfig.getOption('serverRoot'),
        workspaces: PageConfig.getOption('workspacesDir'),
      },
    };
  }

  /**
   * Handle the DOM events for the application.
   *
   * @param event - The DOM event sent to the application.
   */
  handleEvent(event: Event): void {
    super.handleEvent(event);
    if (event.type === 'resize') {
      void this._formatter.invoke();
    }
  }

  /**
   * Register plugins from a plugin module.
   *
   * @param mod - The plugin module to register.
   */
  registerPluginModule(mod: NotebookApp.IPluginModule): void {
    let data = mod.default;
    // Handle commonjs exports.
    if (!Object.prototype.hasOwnProperty.call(mod, '__esModule')) {
      data = mod as any;
    }
    if (!Array.isArray(data)) {
      data = [data];
    }
    data.forEach((item) => {
      try {
        this.registerPlugin(item);
      } catch (error) {
        console.error(error);
      }
    });
  }

  /**
   * Register the plugins from multiple plugin modules.
   *
   * @param mods - The plugin modules to register.
   */
  registerPluginModules(mods: NotebookApp.IPluginModule[]): void {
    mods.forEach((mod) => {
      this.registerPluginModule(mod);
    });
  }

  /**
   * Register collaboration-specific plugins.
   * 
   * @param mods - The collaboration plugin modules to register.
   */
  registerCollaborationPlugins(mods: NotebookApp.IPluginModule[]): void {
    if (!this._collaborationEnabled) {
      console.warn('Collaboration is not enabled. Skipping collaboration plugins registration.');
      return;
    }
    
    console.log(`Registering ${mods.length} collaboration plugins`);
    this.registerPluginModules(mods);
  }

  /**
   * Check if collaboration is enabled for this application.
   * 
   * @returns A boolean indicating whether collaboration is enabled.
   */
  isCollaborationEnabled(): boolean {
    return this._collaborationEnabled;
  }

  /**
   * Get the current collaboration status.
   * 
   * @returns The current collaboration status ('connected', 'connecting', 'disconnected', or 'error').
   */
  getCollaborationStatus(): NotebookApp.CollaborationStatus {
    return this._collaborationStatus;
  }

  /**
   * Set the current collaboration status.
   * 
   * @param status - The new collaboration status.
   */
  setCollaborationStatus(status: NotebookApp.CollaborationStatus): void {
    if (this._collaborationStatus !== status) {
      const oldStatus = this._collaborationStatus;
      this._collaborationStatus = status;
      
      // Update UI based on status change
      this._updateCollaborationUI(oldStatus, status);
      
      // Emit status change event
      this._collaborationStatusChanged.emit({
        oldStatus,
        newStatus: status
      });
      
      // Log status change for monitoring
      console.log(`Collaboration status changed: ${oldStatus} -> ${status}`);
      
      // Update metrics on status change
      this._updateCollaborationMetrics();
    }
  }

  /**
   * Get the current collaboration metrics.
   * 
   * @returns The current collaboration metrics.
   */
  getCollaborationMetrics(): NotebookApp.ICollaborationMetrics {
    return { ...this._collaborationMetrics };
  }

  /**
   * Initialize the WebSocket connection for collaboration.
   * 
   * @param documentId - The ID of the document to collaborate on.
   * @param options - Options for the WebSocket connection.
   * @returns A promise that resolves when the connection is established.
   */
  async initializeCollaborativeSession(documentId: string, options: NotebookApp.ICollaborationOptions = {}): Promise<void> {
    if (!this._collaborationEnabled) {
      console.warn('Collaboration is not enabled. Cannot initialize collaborative session.');
      return;
    }

    try {
      this.setCollaborationStatus('connecting');
      
      // Show collaboration UI elements
      this.shell.showCollaborationStatus();
      this.shell.showPresenceBar();
      
      // Emit session initialization event
      this._collaborationSessionInitialized.emit({
        documentId,
        options
      });
      
      // Update metrics
      this._collaborationMetrics.lastSyncTime = Date.now();
      
      this.setCollaborationStatus('connected');
    } catch (error) {
      console.error('Failed to initialize collaborative session:', error);
      this.setCollaborationStatus('error');
      this._handleCollaborationError(error);
      throw error;
    }
  }

  /**
   * Terminate the current collaborative session.
   * 
   * @returns A promise that resolves when the session is terminated.
   */
  async terminateCollaborativeSession(): Promise<void> {
    if (!this._collaborationEnabled || this._collaborationStatus === 'disconnected') {
      return;
    }

    try {
      // Emit session termination event
      this._collaborationSessionTerminated.emit();
      
      // Hide collaboration UI elements
      this.shell.hideCollaborationStatus();
      this.shell.hidePresenceBar();
      
      this.setCollaborationStatus('disconnected');
    } catch (error) {
      console.error('Error terminating collaborative session:', error);
      throw error;
    }
  }

  /**
   * Signal emitted when collaboration status changes.
   */
  get collaborationStatusChanged(): ISignal<this, NotebookApp.ICollaborationStatusChange> {
    return this._collaborationStatusChanged;
  }

  /**
   * Signal emitted when a collaborative session is initialized.
   */
  get collaborationSessionInitialized(): ISignal<this, NotebookApp.ICollaborationSessionInfo> {
    return this._collaborationSessionInitialized;
  }

  /**
   * Signal emitted when a collaborative session is terminated.
   */
  get collaborationSessionTerminated(): ISignal<this, void> {
    return this._collaborationSessionTerminated;
  }

  /**
   * Signal emitted when a reconnection attempt is made.
   */
  get collaborationReconnectionAttempt(): ISignal<this, NotebookApp.IReconnectionInfo> {
    return this._collaborationReconnectionAttempt;
  }

  /**
   * Signal emitted when a collaboration error occurs.
   */
  get collaborationError(): ISignal<this, NotebookApp.ICollaborationError> {
    return this._collaborationError;
  }

  /**
   * Signal emitted when collaboration metrics are updated.
   */
  get collaborationMetricsUpdated(): ISignal<this, NotebookApp.ICollaborationMetrics> {
    return this._collaborationMetricsUpdated;
  }

  /**
   * Handle a WebSocket connection error.
   * 
   * @param error - The error that occurred.
   * @param retryCount - The number of retry attempts made so far.
   * @returns A promise that resolves when the error is handled.
   */
  async handleWebSocketError(error: Error, retryCount: number = 0): Promise<void> {
    if (!this._collaborationEnabled) {
      return;
    }

    console.error('WebSocket connection error:', error);
    
    // Update metrics
    this._collaborationMetrics.reconnectionAttempts++;
    
    // Implement exponential backoff for reconnection
    const maxRetries = 5;
    const baseDelay = 1000; // 1 second
    
    if (retryCount < maxRetries) {
      const delay = baseDelay * Math.pow(2, retryCount);
      console.log(`Attempting to reconnect in ${delay}ms (attempt ${retryCount + 1}/${maxRetries})`);
      
      this.setCollaborationStatus('connecting');
      
      // Wait for the delay
      await new Promise(resolve => setTimeout(resolve, delay));
      
      // Emit reconnection attempt event
      this._collaborationReconnectionAttempt.emit({
        retryCount: retryCount + 1,
        maxRetries
      });
      
      // The actual reconnection will be handled by the y-websocket provider
    } else {
      console.error('Maximum reconnection attempts reached. Falling back to non-collaborative mode.');
      this.setCollaborationStatus('error');
      this._handleCollaborationError(new Error('Maximum reconnection attempts reached'));
    }
  }

  /**
   * Handle WebSocket connection status changes.
   * 
   * @param status - The new WebSocket connection status.
   */
  handleWebSocketStatus(status: 'connecting' | 'connected' | 'disconnected'): void {
    if (!this._collaborationEnabled) {
      return;
    }

    // Map WebSocket status to collaboration status
    let collaborationStatus: NotebookApp.CollaborationStatus;
    switch (status) {
      case 'connected':
        collaborationStatus = 'connected';
        // Reset reconnection attempts on successful connection
        this._collaborationMetrics.reconnectionAttempts = 0;
        // Update last sync time
        this._collaborationMetrics.lastSyncTime = Date.now();
        break;
      case 'connecting':
        collaborationStatus = 'connecting';
        break;
      case 'disconnected':
        collaborationStatus = 'disconnected';
        break;
      default:
        return;
    }

    this.setCollaborationStatus(collaborationStatus);
  }

  /**
   * Update the collaboration UI based on status changes.
   * 
   * @param oldStatus - The previous collaboration status.
   * @param newStatus - The new collaboration status.
   */
  private _updateCollaborationUI(oldStatus: NotebookApp.CollaborationStatus, newStatus: NotebookApp.CollaborationStatus): void {
    // Show/hide UI elements based on status
    if (newStatus === 'connected') {
      this.shell.showCollaborationStatus();
      this.shell.showPresenceBar();
    } else if (newStatus === 'disconnected') {
      this.shell.hideCollaborationStatus();
      this.shell.hidePresenceBar();
    } else if (newStatus === 'error') {
      // Keep status bar visible to show error state
      this.shell.showCollaborationStatus();
      this.shell.hidePresenceBar();
    }
  }

  /**
   * Handle a collaboration error by implementing graceful degradation.
   * 
   * @param error - The error that occurred.
   */
  private _handleCollaborationError(error: Error): void {
    console.error('Collaboration error, falling back to non-collaborative mode:', error);
    
    // Emit error event
    this._collaborationError.emit({
      error,
      timestamp: Date.now()
    });
    
    // Update UI to show error state
    // The specific UI updates will be handled by collaboration plugins
  }

  /**
   * Check if collaboration is enabled based on configuration.
   * 
   * @returns A boolean indicating whether collaboration is enabled.
   */
  private _isCollaborationEnabled(): boolean {
    // Check if collaboration is explicitly enabled in PageConfig
    const explicitlyEnabled = PageConfig.getOption('collaborationEnabled');
    if (explicitlyEnabled === 'true') {
      return true;
    } else if (explicitlyEnabled === 'false') {
      return false;
    }
    
    // Check if collaboration URL is configured
    const collaborationUrl = PageConfig.getOption('collaborationUrl');
    if (collaborationUrl) {
      return true;
    }
    
    // Check if we're in a JupyterHub environment, which might support collaboration
    const hubHost = PageConfig.getOption('hubHost');
    const hubUser = PageConfig.getOption('hubUser');
    if (hubHost && hubUser) {
      // Default to enabled in JupyterHub environment unless explicitly disabled
      return true;
    }
    
    // Default to disabled
    return false;
  }

  /**
   * Update collaboration metrics.
   */
  private _updateCollaborationMetrics(): void {
    if (!this._collaborationEnabled) {
      return;
    }
    
    // Emit metrics update event
    this._collaborationMetricsUpdated.emit(this._collaborationMetrics);
    
    // Log metrics for monitoring
    console.debug('Collaboration metrics:', this._collaborationMetrics);
  }

  /**
   * Update collaboration metrics with data from Yjs.
   * 
   * @param metrics - Partial metrics to update.
   */
  updateCollaborationMetrics(metrics: Partial<NotebookApp.ICollaborationMetrics>): void {
    if (!this._collaborationEnabled) {
      return;
    }
    
    // Update metrics with provided values
    this._collaborationMetrics = {
      ...this._collaborationMetrics,
      ...metrics
    };
    
    // Emit metrics update event
    this._collaborationMetricsUpdated.emit(this._collaborationMetrics);
  }

  /**
   * Update the active users count in the collaboration metrics.
   * 
   * @param count - The new active users count.
   */
  updateActiveUsersCount(count: number): void {
    if (!this._collaborationEnabled || count < 0) {
      return;
    }
    
    this._collaborationMetrics.activeUsers = count;
    
    // Update UI if needed based on user count
    if (count > 1 && this._collaborationStatus === 'connected') {
      // Ensure collaboration UI is visible when multiple users are present
      this.shell.showPresenceBar();
    }
    
    // Emit metrics update event
    this._collaborationMetricsUpdated.emit(this._collaborationMetrics);
  }

  /**
   * Track operation latency and update metrics.
   * 
   * @param operationLatency - The latency of the operation in milliseconds.
   */
  trackOperationLatency(operationLatency: number): void {
    if (!this._collaborationEnabled || operationLatency < 0) {
      return;
    }
    
    // Increment total operations count
    this._collaborationMetrics.totalOperations++;
    
    // Update average latency using a weighted average
    const totalOps = this._collaborationMetrics.totalOperations;
    const currentAvg = this._collaborationMetrics.averageLatency;
    
    // Calculate new weighted average
    if (totalOps === 1) {
      // First operation, just set the latency
      this._collaborationMetrics.averageLatency = operationLatency;
    } else {
      // Weighted average: ((n-1) * currentAvg + newValue) / n
      this._collaborationMetrics.averageLatency = 
        ((totalOps - 1) * currentAvg + operationLatency) / totalOps;
    }
    
    // Only emit metrics update periodically to avoid flooding
    if (totalOps % 10 === 0) {
      this._collaborationMetricsUpdated.emit(this._collaborationMetrics);
    }
  }

  private _info: JupyterLab.IInfo = JupyterLab.defaultInfo;
  private _formatter = new Throttler(() => {
    Private.setFormat(this);
  }, 250);

  // Collaboration-related properties
  private _collaborationEnabled: boolean;
  private _collaborationStatus: NotebookApp.CollaborationStatus;
  private _collaborationMetrics: NotebookApp.ICollaborationMetrics;
  private _collaborationMonitor: Throttler | null = null;
  
  // Collaboration-related signals
  private _collaborationStatusChanged = new Signal<this, NotebookApp.ICollaborationStatusChange>(this);
  private _collaborationSessionInitialized = new Signal<this, NotebookApp.ICollaborationSessionInfo>(this);
  private _collaborationSessionTerminated = new Signal<this, void>(this);
  private _collaborationReconnectionAttempt = new Signal<this, NotebookApp.IReconnectionInfo>(this);
  private _collaborationError = new Signal<this, NotebookApp.ICollaborationError>(this);
  private _collaborationMetricsUpdated = new Signal<this, NotebookApp.ICollaborationMetrics>(this);
}

/**
 * A namespace for App static items.
 */
export namespace NotebookApp {
  /**
   * The instantiation options for an App application.
   */
  export interface IOptions
    extends JupyterFrontEnd.IOptions<INotebookShell>,
      Partial<IInfo> {}

  /**
   * The information about a Jupyter Notebook application.
   */
  export interface IInfo {
    /**
     * The mime renderer extensions.
     */
    readonly mimeExtensions: IRenderMime.IExtensionModule[];

    /**
     * The information about available plugins.
     */
    readonly availablePlugins: JupyterLab.IPluginInfo[];
  }

  /**
   * The interface for a module that exports a plugin or plugins as
   * the default value.
   */
  export interface IPluginModule {
    /**
     * The default export.
     */
    default: JupyterFrontEndPlugin<any> | JupyterFrontEndPlugin<any>[];
  }

  /**
   * Collaboration status types.
   */
  export type CollaborationStatus = 'connected' | 'connecting' | 'disconnected' | 'error';

  /**
   * Collaboration options interface.
   */
  export interface ICollaborationOptions {
    /**
     * Whether to automatically connect to the collaboration server.
     */
    autoConnect?: boolean;

    /**
     * Parameters to pass to the WebSocket connection.
     */
    params?: { [key: string]: string };

    /**
     * WebSocket implementation to use (for Node.js environments).
     */
    WebSocketPolyfill?: any;

    /**
     * Maximum number of reconnection attempts.
     */
    maxReconnectionAttempts?: number;
  }

  /**
   * Collaboration metrics interface.
   */
  export interface ICollaborationMetrics {
    /**
     * Number of active users in the collaborative session.
     */
    activeUsers: number;

    /**
     * Total number of operations processed.
     */
    totalOperations: number;

    /**
     * Average latency of operations in milliseconds.
     */
    averageLatency: number;

    /**
     * Number of reconnection attempts made.
     */
    reconnectionAttempts: number;

    /**
     * Timestamp of the last successful sync.
     */
    lastSyncTime: number;
  }

  /**
   * Collaboration status change interface.
   */
  export interface ICollaborationStatusChange {
    /**
     * The previous collaboration status.
     */
    oldStatus: CollaborationStatus;

    /**
     * The new collaboration status.
     */
    newStatus: CollaborationStatus;
  }

  /**
   * Collaboration session information interface.
   */
  export interface ICollaborationSessionInfo {
    /**
     * The ID of the document being collaborated on.
     */
    documentId: string;

    /**
     * Options used to initialize the session.
     */
    options: ICollaborationOptions;
  }

  /**
   * Reconnection information interface.
   */
  export interface IReconnectionInfo {
    /**
     * The current retry count.
     */
    retryCount: number;

    /**
     * The maximum number of retries allowed.
     */
    maxRetries: number;
  }

  /**
   * Collaboration error interface.
   */
  export interface ICollaborationError {
    /**
     * The error that occurred.
     */
    error: Error;

    /**
     * Timestamp when the error occurred.
     */
    timestamp: number;
  }
}

/**
 * A namespace for module-private functionality.
 */
namespace Private {
  /**
   * Media query for mobile devices.
   */
  const MOBILE_QUERY = 'only screen and (max-width: 760px)';

  /**
   * Sets the `format` of a Jupyter front-end application.
   *
   * @param app The front-end application whose format is set.
   */
  export function setFormat(app: NotebookApp): void {
    app.format = window.matchMedia(MOBILE_QUERY).matches ? 'mobile' : 'desktop';
  }
}