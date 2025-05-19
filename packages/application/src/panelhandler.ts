// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ICommandPalette } from '@jupyterlab/apputils';
import { closeIcon } from '@jupyterlab/ui-components';
import { ArrayExt, find } from '@lumino/algorithm';
import { IDisposable } from '@lumino/disposable';
import { IMessageHandler, Message, MessageLoop } from '@lumino/messaging';
import { ISignal, Signal } from '@lumino/signaling';
import { Panel, StackedPanel, Widget } from '@lumino/widgets';

/**
 * A class which manages a panel and sorts its widgets by rank.
 */
export class PanelHandler {
  constructor() {
    MessageLoop.installMessageHook(this._panel, this._panelChildHook);
  }

  /**
   * Get the panel managed by the handler.
   */
  get panel(): Panel {
    return this._panel;
  }

  /**
   * Add a widget to the panel.
   *
   * If the widget is already added, it will be moved.
   */
  addWidget(widget: Widget, rank: number): void {
    widget.parent = null;
    const item = { widget, rank };
    const index = ArrayExt.upperBound(this._items, item, Private.itemCmp);
    ArrayExt.insert(this._items, index, item);
    this._panel.insertWidget(index, widget);
  }

  /**
   * Add a collaboration-specific widget to the panel.
   * 
   * This method allows for special handling of collaboration widgets.
   * 
   * @param widget - The collaboration widget to add
   * @param rank - The rank of the widget
   * @param options - Optional collaboration-specific options
   */
  addCollaborationWidget(widget: Widget, rank: number, options?: CollaborationWidgetOptions): void {
    widget.parent = null;
    const item = { 
      widget, 
      rank,
      isCollaborationWidget: true,
      collaborationOptions: options || {}
    };
    const index = ArrayExt.upperBound(this._items, item, Private.itemCmp);
    ArrayExt.insert(this._items, index, item);
    this._panel.insertWidget(index, widget);
    
    // Add collaboration-specific class to the widget for styling
    widget.addClass('jp-CollaborationWidget');
  }

  /**
   * Get all collaboration widgets in this panel.
   */
  getCollaborationWidgets(): Widget[] {
    return this._items
      .filter(item => 'isCollaborationWidget' in item && item.isCollaborationWidget)
      .map(item => item.widget);
  }

  /**
   * A message hook for child remove messages on the panel handler.
   */
  private _panelChildHook = (
    handler: IMessageHandler,
    msg: Message
  ): boolean => {
    switch (msg.type) {
      case 'child-removed':
        {
          const widget = (msg as Widget.ChildMessage).child;
          ArrayExt.removeFirstWhere(this._items, (v) => v.widget === widget);
        }
        break;
      default:
        break;
    }
    return true;
  };

  protected _items = new Array<Private.IRankItem>();
  protected _panel = new Panel();
}

/**
 * A class which manages a side panel that can show at most one widget at a time.
 */
export class SidePanelHandler extends PanelHandler {
  /**
   * Construct a new side panel handler.
   */
  constructor(area: SidePanel.Area) {
    super();
    this._area = area;
    this._panel.hide();

    this._currentWidget = null;
    this._lastCurrentWidget = null;

    this._widgetPanel = new StackedPanel();
    this._widgetPanel.widgetRemoved.connect(this._onWidgetRemoved, this);

    this._closeButton = document.createElement('button');
    closeIcon.element({
      container: this._closeButton,
      height: '16px',
      width: 'auto',
    });
    this._closeButton.onclick = () => {
      this.collapse();
      this.hide();
    };
    this._closeButton.className = 'jp-Button jp-SidePanel-collapse';
    this._closeButton.title = 'Collapse side panel';

    const icon = new Widget({ node: this._closeButton });
    this._panel.addWidget(icon);
    this._panel.addWidget(this._widgetPanel);
    
    // Initialize collaboration status indicator container
    this._collaborationStatusContainer = document.createElement('div');
    this._collaborationStatusContainer.className = 'jp-SidePanel-collaborationStatus';
    this._collaborationStatusContainer.style.display = 'none';
    
    // Add collaboration status container to the panel
    const statusWidget = new Widget({ node: this._collaborationStatusContainer });
    this._panel.addWidget(statusWidget);
  }

  /**
   * Get the current widget in the sidebar panel.
   */
  get currentWidget(): Widget | null {
    return (
      this._currentWidget ||
      this._lastCurrentWidget ||
      (this._items.length > 0 ? this._items[0].widget : null)
    );
  }

  /**
   * Get the area of the side panel
   */
  get area(): SidePanel.Area {
    return this._area;
  }

  /**
   * Whether the panel is visible
   */
  get isVisible(): boolean {
    return this._panel.isVisible;
  }

  /**
   * Get the stacked panel managed by the handler
   */
  get panel(): Panel {
    return this._panel;
  }

  /**
   * Get the widgets list.
   */
  get widgets(): Readonly<Widget[]> {
    return this._items.map((obj) => obj.widget);
  }

  /**
   * Signal fired when a widget is added to the panel
   */
  get widgetAdded(): ISignal<SidePanelHandler, Widget> {
    return this._widgetAdded;
  }

  /**
   * Signal fired when a widget is removed from the panel
   */
  get widgetRemoved(): ISignal<SidePanelHandler, Widget> {
    return this._widgetRemoved;
  }

  /**
   * Get the close button element.
   */
  get closeButton(): HTMLButtonElement {
    return this._closeButton;
  }

  /**
   * Get the collaboration status container element.
   */
  get collaborationStatusContainer(): HTMLDivElement {
    return this._collaborationStatusContainer;
  }

  /**
   * Set the collaboration status for this panel.
   * 
   * @param status - The collaboration status to set
   */
  setCollaborationStatus(status: CollaborationStatus | null): void {
    if (!status) {
      this._collaborationStatusContainer.style.display = 'none';
      return;
    }
    
    // Update the status container with the new status
    this._collaborationStatusContainer.style.display = 'flex';
    this._collaborationStatusContainer.innerHTML = '';
    
    // Create status indicator
    const statusIndicator = document.createElement('div');
    statusIndicator.className = `jp-CollaborationStatus-indicator jp-CollaborationStatus-${status.state}`;
    this._collaborationStatusContainer.appendChild(statusIndicator);
    
    // Create status text
    const statusText = document.createElement('span');
    statusText.textContent = status.message;
    statusText.className = 'jp-CollaborationStatus-text';
    this._collaborationStatusContainer.appendChild(statusText);
    
    // Add user presence indicators if available
    if (status.activeUsers && status.activeUsers.length > 0) {
      const presenceContainer = document.createElement('div');
      presenceContainer.className = 'jp-CollaborationStatus-presence';
      
      // Add up to 3 user avatars, with a +N indicator for additional users
      const maxVisibleUsers = 3;
      const visibleUsers = status.activeUsers.slice(0, maxVisibleUsers);
      const remainingUsers = Math.max(0, status.activeUsers.length - maxVisibleUsers);
      
      visibleUsers.forEach(user => {
        const userAvatar = document.createElement('div');
        userAvatar.className = 'jp-CollaborationStatus-userAvatar';
        userAvatar.title = user.displayName;
        userAvatar.style.backgroundColor = user.color;
        userAvatar.textContent = user.displayName.substring(0, 1).toUpperCase();
        presenceContainer.appendChild(userAvatar);
      });
      
      if (remainingUsers > 0) {
        const remainingIndicator = document.createElement('div');
        remainingIndicator.className = 'jp-CollaborationStatus-remainingUsers';
        remainingIndicator.textContent = `+${remainingUsers}`;
        presenceContainer.appendChild(remainingIndicator);
      }
      
      this._collaborationStatusContainer.appendChild(presenceContainer);
    }
  }

  /**
   * Add a collaboration-specific widget to the side panel.
   * 
   * @param widget - The collaboration widget to add
   * @param rank - The rank of the widget
   * @param options - Optional collaboration-specific options
   */
  addCollaborationWidget(widget: Widget, rank: number, options?: CollaborationWidgetOptions): void {
    widget.parent = null;
    widget.hide();
    const item = { 
      widget, 
      rank,
      isCollaborationWidget: true,
      collaborationOptions: options || {}
    };
    const index = this._findInsertIndex(item);
    ArrayExt.insert(this._items, index, item);
    this._widgetPanel.insertWidget(index, widget);

    // Add collaboration-specific class to the widget for styling
    widget.addClass('jp-CollaborationWidget');
    
    this._refreshVisibility();

    this._widgetAdded.emit(widget);
  }

  /**
   * Expand the sidebar.
   *
   * #### Notes
   * This will open the most recently used widget, or the first widget
   * if there is no most recently used.
   */
  expand(id?: string): void {
    if (id) {
      if (this._currentWidget && this._currentWidget.id === id) {
        this.collapse();
        this.hide();
      } else {
        this.collapse();
        this.hide();
        this.activate(id);
        this.show();
      }
    } else if (this.currentWidget) {
      this._currentWidget = this.currentWidget;
      this.activate(this._currentWidget.id);
      this.show();
    }
  }

  /**
   * Activate a widget residing in the stacked panel by ID.
   *
   * @param id - The widget's unique ID.
   */
  activate(id: string): void {
    const widget = this._findWidgetByID(id);
    if (widget) {
      this._currentWidget = widget;
      widget.show();
      widget.activate();
    }
  }

  /**
   * Test whether the sidebar has the given widget by id.
   */
  has(id: string): boolean {
    return this._findWidgetByID(id) !== null;
  }

  /**
   * Collapse the sidebar so no items are expanded.
   */
  collapse(): void {
    this._currentWidget?.hide();
    this._currentWidget = null;
  }

  /**
   * Add a widget and its title to the stacked panel.
   *
   * If the widget is already added, it will be moved.
   */
  addWidget(widget: Widget, rank: number): void {
    widget.parent = null;
    widget.hide();
    const item = { widget, rank };
    const index = this._findInsertIndex(item);
    ArrayExt.insert(this._items, index, item);
    this._widgetPanel.insertWidget(index, widget);

    this._refreshVisibility();

    this._widgetAdded.emit(widget);
  }

  /**
   * Hide the side panel
   */
  hide(): void {
    this._isHiddenByUser = true;
    this._refreshVisibility();
  }

  /**
   * Show the side panel
   */
  show(): void {
    this._isHiddenByUser = false;
    this._refreshVisibility();
  }

  /**
   * Find the insertion index for a rank item.
   */
  private _findInsertIndex(item: Private.IRankItem): number {
    return ArrayExt.upperBound(this._items, item, Private.itemCmp);
  }

  /**
   * Find the index of the item with the given widget, or `-1`.
   */
  private _findWidgetIndex(widget: Widget): number {
    return ArrayExt.findFirstIndex(this._items, (i) => i.widget === widget);
  }

  /**
   * Find the widget with the given id, or `null`.
   */
  private _findWidgetByID(id: string): Widget | null {
    const item = find(this._items, (value) => value.widget.id === id);
    return item ? item.widget : null;
  }

  /**
   * Refresh the visibility of the stacked panel.
   */
  private _refreshVisibility(): void {
    this._panel.setHidden(this._isHiddenByUser);
  }

  /*
   * Handle the `widgetRemoved` signal from the panel.
   */
  private _onWidgetRemoved(sender: StackedPanel, widget: Widget): void {
    if (widget === this._lastCurrentWidget) {
      this._lastCurrentWidget = null;
    }
    ArrayExt.removeAt(this._items, this._findWidgetIndex(widget));

    this._refreshVisibility();

    this._widgetRemoved.emit(widget);
  }

  private _area: SidePanel.Area;
  private _isHiddenByUser = false;
  private _widgetPanel: StackedPanel;
  private _currentWidget: Widget | null;
  private _lastCurrentWidget: Widget | null;
  private _closeButton: HTMLButtonElement;
  private _collaborationStatusContainer: HTMLDivElement;
  private _widgetAdded: Signal<SidePanelHandler, Widget> = new Signal(this);
  private _widgetRemoved: Signal<SidePanelHandler, Widget> = new Signal(this);
}

/**
 * A name space for SideBarPanel functions.
 */
export namespace SidePanel {
  /**
   * The areas of the sidebar panel
   */
  export type Area = 'left' | 'right';
}

/**
 * A class to manages the palette entries associated to the side panels.
 */
export class SidePanelPalette {
  /**
   * Construct a new side panel palette.
   */
  constructor(options: SidePanelPaletteOption) {
    this._commandPalette = options.commandPalette;
    this._command = options.command;
  }

  /**
   * Get a command palette item from the widget id and the area.
   */
  getItem(
    widget: Readonly<Widget>,
    area: 'left' | 'right'
  ): SidePanelPaletteItem | null {
    const itemList = this._items;
    for (let i = 0; i < itemList.length; i++) {
      const item = itemList[i];
      if (item.widgetId === widget.id && item.area === area) {
        return item;
      }
    }
    return null;
  }

  /**
   * Add an item to the command palette.
   */
  addItem(widget: Readonly<Widget>, area: 'left' | 'right'): void {
    // Check if the item does not already exist.
    if (this.getItem(widget, area)) {
      return;
    }

    // Add a new item in command palette.
    const disposableDelegate = this._commandPalette.addItem({
      command: this._command,
      category: 'View',
      args: {
        side: area,
        title: `Show ${widget.title.caption}`,
        id: widget.id,
      },
    });

    // Keep the disposableDelegate object to be able to dispose of the item if the widget
    // is remove from the side panel.
    this._items.push({
      widgetId: widget.id,
      area: area,
      disposable: disposableDelegate,
    });
  }

  /**
   * Add a collaboration-specific item to the command palette.
   * 
   * @param widget - The collaboration widget
   * @param area - The area of the panel
   * @param category - Optional category for the command palette entry (defaults to 'Collaboration')
   */
  addCollaborationItem(widget: Readonly<Widget>, area: 'left' | 'right', category: string = 'Collaboration'): void {
    // Check if the item does not already exist.
    if (this.getItem(widget, area)) {
      return;
    }

    // Add a new item in command palette with collaboration-specific category.
    const disposableDelegate = this._commandPalette.addItem({
      command: this._command,
      category: category,
      args: {
        side: area,
        title: `Show ${widget.title.caption}`,
        id: widget.id,
        isCollaboration: true
      },
    });

    // Keep the disposableDelegate object to be able to dispose of the item if the widget
    // is remove from the side panel.
    this._items.push({
      widgetId: widget.id,
      area: area,
      disposable: disposableDelegate,
      isCollaboration: true
    });
  }

  /**
   * Remove an item from the command palette.
   */
  removeItem(widget: Readonly<Widget>, area: 'left' | 'right'): void {
    const item = this.getItem(widget, area);
    if (item) {
      item.disposable.dispose();
    }
  }

  _command: string;
  _commandPalette: ICommandPalette;
  _items: SidePanelPaletteItem[] = [];
}

/**
 * Interface for a side panel palette item.
 */
type SidePanelPaletteItem = {
  /**
   * The ID of the widget associated to the command palette.
   */
  widgetId: string;

  /**
   * The area of the panel associated to the command palette.
   */
  area: 'left' | 'right';

  /**
   * The disposable object to remove the item from command palette.
   */
  disposable: IDisposable;
  
  /**
   * Whether this is a collaboration-specific item.
   */
  isCollaboration?: boolean;
};

/**
 * An interface for the options to include in SideBarPalette constructor.
 */
type SidePanelPaletteOption = {
  /**
   * The commands palette.
   */
  commandPalette: ICommandPalette;

  /**
   * The command to call from each side panel menu entry.
   *
   * ### Notes
   * That command required 3 args :
   *      side: 'left' | 'right', the area to toggle
   *      title: string, label of the command
   *      id: string, id of the widget to activate
   */
  command: string;
};

/**
 * Interface for collaboration widget options.
 */
export interface CollaborationWidgetOptions {
  /**
   * The type of collaboration widget.
   */
  type?: 'presence' | 'history' | 'comments' | 'permissions' | 'locks' | 'other';
  
  /**
   * Whether this widget should be shown in the collaboration status area.
   */
  showInStatusArea?: boolean;
  
  /**
   * Additional metadata for the collaboration widget.
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for collaboration status.
 */
export interface CollaborationStatus {
  /**
   * The state of the collaboration.
   */
  state: 'connected' | 'connecting' | 'disconnected' | 'error';
  
  /**
   * A message describing the current status.
   */
  message: string;
  
  /**
   * List of active users in the collaboration session.
   */
  activeUsers?: Array<{
    /**
     * Unique identifier for the user.
     */
    id: string;
    
    /**
     * Display name for the user.
     */
    displayName: string;
    
    /**
     * Color associated with this user for UI elements.
     */
    color: string;
    
    /**
     * Optional avatar URL.
     */
    avatarUrl?: string;
  }>;
}

/**
 * A namespace for private module data.
 */
namespace Private {
  /**
   * An object which holds a widget and its sort rank.
   */
  export interface IRankItem {
    /**
     * The widget for the item.
     */
    widget: Widget;

    /**
     * The sort rank of the widget.
     */
    rank: number;
    
    /**
     * Whether this is a collaboration widget.
     */
    isCollaborationWidget?: boolean;
    
    /**
     * Collaboration-specific options for the widget.
     */
    collaborationOptions?: CollaborationWidgetOptions;
  }
  /**
   * A less-than comparison function for side bar rank items.
   */
  export function itemCmp(first: IRankItem, second: IRankItem): number {
    return first.rank - second.rank;
  }
}