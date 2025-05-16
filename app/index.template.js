// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

// Inspired by: https://github.com/jupyterlab/jupyterlab/blob/master/dev_mode/index.js

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

import { PluginRegistry } from '@lumino/coreutils';

// Import Yjs and related modules for collaborative editing
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { Awareness } from 'y-protocols/awareness';

require('./style.js');
require('./extraStyle.js');

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const newScript = document.createElement('script');
    newScript.onerror = reject;
    newScript.onload = resolve;
    newScript.async = true;
    document.head.appendChild(newScript);
    newScript.src = url;
  });
}
async function loadComponent(url, scope) {
  await loadScript(url);

  // From MIT-licensed https://github.com/module-federation/module-federation-examples/blob/af043acd6be1718ee195b2511adf6011fba4233c/advanced-api/dynamic-remotes/app1/src/App.js#L6-L12
  // eslint-disable-next-line no-undef
  await __webpack_init_sharing__('default');
  const container = window._JUPYTERLAB[scope];
  // Initialize the container, it may provide shared modules and may need ours
  // eslint-disable-next-line no-undef
  await container.init(__webpack_share_scopes__.default);
}

async function createModule(scope, module) {
  try {
    const factory = await window._JUPYTERLAB[scope].get(module);
    const instance = factory();
    instance.__scope__ = scope;
    return instance;
  } catch (e) {
    console.warn(
      `Failed to create module: package: ${scope}; module: ${module}`
    );
    throw e;
  }
}

/**
 * Initialize the Yjs document and providers for collaborative editing
 * @param {string} docId - The document identifier
 * @param {Object} options - Configuration options
 * @returns {Object} - The initialized collaboration objects
 */
async function initializeCollaboration(docId, options = {}) {
  try {
    // Initialize the Yjs document
    const yjsDoc = new Y.Doc();
    
    // Get the WebSocket URL from options or use default
    const websocketUrl = options.websocketUrl || 
                        (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
                        window.location.host + '/collaboration';
    
    // Initialize the WebSocket provider for real-time synchronization
    const websocketProvider = new WebsocketProvider(websocketUrl, docId, yjsDoc, {
      connect: true,
      params: options.params || {}
    });
    
    // Get awareness instance from the provider
    const awareness = websocketProvider.awareness;
    
    // Set initial awareness state if user info is provided
    if (options.user) {
      awareness.setLocalStateField('user', {
        name: options.user.name || 'Anonymous',
        color: options.user.color || '#' + Math.floor(Math.random() * 16777215).toString(16),
        clientId: yjsDoc.clientID
      });
    }
    
    return { yjsDoc, websocketProvider, awareness };
  } catch (error) {
    console.error('Failed to initialize collaboration:', error);
    throw error;
  }
}

/**
 * The main function
 */
async function main() {
  const mimeExtensionsMods = [
  {{#each notebook_mime_extensions}}
    require('{{ @key }}'),
  {{/each}}
  ];
  const mimeExtensions = await Promise.all(mimeExtensionsMods);

  // Load the base plugins available on all pages
  let baseMods = [
  {{#each notebook_plugins}}
    {{#if (ispage @key '/')}}
      {{{ list_plugins }}}
    {{/if}}
  {{/each}}
  ];

  const page = `/${PageConfig.getOption('notebookPage')}`;
  switch (page) {
  {{#each notebook_plugins}}
    {{#unless (ispage @key '/')}}
    // list all the other plugins grouped by page
    case '{{ @key }}': {
      baseMods = baseMods.concat([
        {{{ list_plugins }}}
      ]);
      break;
    }
    {{/unless}}
  {{/each}}
  }

  // populate the list of disabled extensions
  const disabled = [];
  const availablePlugins = [];

  /**
   * Iterate over active plugins in an extension.
   *
   * #### Notes
   * This also populates the disabled
   */
  function* activePlugins(extension) {
    // Handle commonjs or es2015 modules
    let exports;
    if (Object.prototype.hasOwnProperty.call(extension, '__esModule')) {
      exports = extension.default;
    } else {
      // CommonJS exports.
      exports = extension;
    }

    let plugins = Array.isArray(exports) ? exports : [exports];
    for (let plugin of plugins) {
      const isDisabled = PageConfig.Extension.isDisabled(plugin.id);
      availablePlugins.push({
        id: plugin.id,
        description: plugin.description,
        requires: plugin.requires ?? [],
        optional: plugin.optional ?? [],
        provides: plugin.provides ?? null,
        autoStart: plugin.autoStart,
        enabled: !isDisabled,
        extension: extension.__scope__
      });
      if (isDisabled) {
        disabled.push(plugin.id);
        continue;
      }
      yield plugin;
    }
  }

  const extension_data = JSON.parse(
    PageConfig.getOption('federated_extensions')
  );

  const mods = [];
  const federatedExtensionPromises = [];
  const federatedMimeExtensionPromises = [];
  const federatedStylePromises = [];

  const extensions = await Promise.allSettled(
    extension_data.map(async data => {
      await loadComponent(
        `${URLExt.join(
          PageConfig.getOption('fullLabextensionsUrl'),
          data.name,
          data.load
        )}`,
        data.name
      );
      return data;
    })
  );

  extensions.forEach(p => {
    if (p.status === 'rejected') {
      // There was an error loading the component
      console.error(p.reason);
      return;
    }

    const data = p.value;
    if (data.extension) {
      federatedExtensionPromises.push(createModule(data.name, data.extension));
    }
    if (data.mimeExtension) {
      federatedMimeExtensionPromises.push(
        createModule(data.name, data.mimeExtension)
      );
    }
    if (data.style && !PageConfig.Extension.isDisabled(data.name)) {
      federatedStylePromises.push(createModule(data.name, data.style));
    }
  });

  // Add the base frontend extensions
  const baseFrontendMods = await Promise.all(baseMods);
  baseFrontendMods.forEach(p => {
    for (let plugin of activePlugins(p)) {
      mods.push(plugin);
    }
  });

  // Add the federated extensions.
  const federatedExtensions = await Promise.allSettled(
    federatedExtensionPromises
  );
  federatedExtensions.forEach(p => {
    if (p.status === 'fulfilled') {
      for (let plugin of activePlugins(p.value)) {
        mods.push(plugin);
      }
    } else {
      console.error(p.reason);
    }
  });

  // Add the federated mime extensions.
  const federatedMimeExtensions = await Promise.allSettled(
    federatedMimeExtensionPromises
  );
  federatedMimeExtensions.forEach(p => {
    if (p.status === 'fulfilled') {
      for (let plugin of activePlugins(p.value)) {
        mimeExtensions.push(plugin);
      }
    } else {
      console.error(p.reason);
    }
  });

  // Load all federated component styles and log errors for any that do not
  (await Promise.allSettled(federatedStylePromises))
    .filter(({ status }) => status === 'rejected')
    .forEach(({ reason }) => {
      console.error(reason);
    });

  // Set the list of base notebook multi-page plugins so the app is aware of all
  // its built-in plugins even if they are not loaded on the current page.
  // For example this is useful so the Settings Editor can list the debugger
  // plugin even if the debugger is only loaded on the notebook page.
  PageConfig.setOption('allPlugins', '{{{ json notebook_plugins }}}');


  const pluginRegistry = new PluginRegistry();
  const NotebookApp = require('@jupyter-notebook/application').NotebookApp;

  pluginRegistry.registerPlugins(mods);
  const IServiceManager = require('@jupyterlab/services').IServiceManager;
  const serviceManager = await pluginRegistry.resolveRequiredService(IServiceManager);
  
  // Initialize Yjs collaborative editing if enabled
  const collaborationEnabled = (PageConfig.getOption('collaborationEnabled') || '').toLowerCase() === 'true';
  let yjsDoc = null;
  let websocketProvider = null;
  let awareness = null;
  
  if (collaborationEnabled) {
    try {
      // Get the document ID from the URL or generate a unique one
      const docId = PageConfig.getOption('docId') || window.location.pathname.split('/').pop() || 'unnamed-document';
      
      // Initialize the Yjs document
      yjsDoc = new Y.Doc();
      
      // Get the WebSocket URL from configuration or use default
      const websocketUrl = PageConfig.getOption('collaborationWsUrl') || 
                          (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
                          window.location.host + '/collaboration';
      
      // Initialize the WebSocket provider for real-time synchronization
      websocketProvider = new WebsocketProvider(websocketUrl, docId, yjsDoc, {
        connect: true,
        params: {
          // Add authentication token if available
          token: PageConfig.getToken() || ''
        }
      });
      
      // Initialize awareness for user presence tracking
      awareness = websocketProvider.awareness;
      
      // Set initial awareness state with user information
      const username = PageConfig.getOption('username') || 'Anonymous';
      awareness.setLocalStateField('user', {
        name: username,
        color: '#' + Math.floor(Math.random() * 16777215).toString(16), // Random color
        clientId: yjsDoc.clientID
      });
      
      // Handle connection status changes
      websocketProvider.on('status', event => {
        console.log('Collaboration status:', event.status);
        // Dispatch a custom event that UI components can listen to
        window.dispatchEvent(new CustomEvent('collaboration-status-change', { 
          detail: { status: event.status } 
        }));
      });
      
      // Log when document sync is complete
      websocketProvider.on('sync', isSynced => {
        console.log('Document synchronized:', isSynced);
        window.dispatchEvent(new CustomEvent('collaboration-sync', { 
          detail: { synced: isSynced } 
        }));
      });
      
      console.log('Collaborative editing initialized with document ID:', docId);
    } catch (error) {
      console.error('Failed to initialize collaborative editing:', error);
      // Dispatch error event for UI components to handle
      window.dispatchEvent(new CustomEvent('collaboration-error', { 
        detail: { error: error.message } 
      }));
    }
  }

  const app = new NotebookApp({
    pluginRegistry,
    serviceManager,
    mimeExtensions,
    availablePlugins,
    // Pass collaborative editing components to the application if enabled
    collaboration: collaborationEnabled ? {
      yjsDoc,
      websocketProvider,
      awareness
    } : null
  });

  // Expose global app instance when in dev mode or when toggled explicitly.
  const exposeAppInBrowser =
    (PageConfig.getOption('exposeAppInBrowser') || '').toLowerCase() === 'true';

  if (exposeAppInBrowser) {
    window.jupyterapp = app;
    
    // Also expose collaboration objects when in dev mode for debugging
    if (collaborationEnabled) {
      window.yjsDoc = yjsDoc;
      window.websocketProvider = websocketProvider;
      window.awareness = awareness;
    }
  }

  await app.start();
  
  // Register event handlers for collaboration error recovery
  if (collaborationEnabled && websocketProvider) {
    // Handle WebSocket connection errors
    websocketProvider.on('connection-error', error => {
      console.error('Collaboration connection error:', error);
      // Attempt to reconnect after a delay
      setTimeout(() => {
        if (websocketProvider) {
          console.log('Attempting to reconnect collaborative session...');
          websocketProvider.connect();
        }
      }, 5000); // 5 second delay before reconnection attempt
    });
    
    // Handle WebSocket connection close
    websocketProvider.on('connection-close', event => {
      console.log('Collaboration connection closed:', event.code, event.reason);
      // Only attempt to reconnect for abnormal closures
      if (event.code !== 1000) { // 1000 is normal closure
        setTimeout(() => {
          if (websocketProvider) {
            console.log('Attempting to reconnect collaborative session...');
            websocketProvider.connect();
          }
        }, 5000); // 5 second delay before reconnection attempt
      }
    });
    
    // Handle window beforeunload to clean up awareness state
    window.addEventListener('beforeunload', () => {
      if (awareness) {
        // Clear local awareness state to signal to other users that we're leaving
        awareness.setLocalState(null);
      }
    });
  }
}

window.addEventListener('load', main);