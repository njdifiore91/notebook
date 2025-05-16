// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

// Inspired by: https://github.com/jupyterlab/jupyterlab/blob/master/dev_mode/index.js

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

import { PluginRegistry } from '@lumino/coreutils';

// Import Yjs and related libraries for collaborative editing
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
 * Initialize Yjs document and providers for collaborative editing
 */
function initCollaboration(app) {
  // Check if collaboration is enabled in configuration
  const isCollabEnabled = (PageConfig.getOption('enableCollaboration') || '').toLowerCase() === 'true';
  if (!isCollabEnabled) {
    console.log('Collaborative editing is disabled. Enable it in server configuration.');
    return null;
  }

  try {
    // Create a Yjs document to store shared data
    const ydoc = new Y.Doc();
    
    // Get the WebSocket URL from configuration or use default
    const websocketUrl = PageConfig.getOption('collaborationWebsocketUrl') || 
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/collaboration`;
    
    // Get the room name (notebook path) from configuration
    const notebookPath = PageConfig.getOption('notebookPath') || 'unnamed-notebook';
    
    // Initialize the WebSocket provider for real-time synchronization
    const websocketProvider = new WebsocketProvider(websocketUrl, notebookPath, ydoc, {
      connect: true,
      awareness: new Awareness(ydoc),
      params: {
        // Add authentication token if available
        token: PageConfig.getToken() || ''
      }
    });
    
    // Set up event listeners for connection status
    websocketProvider.on('status', event => {
      console.log(`Collaboration status: ${event.status}`);
      // Dispatch a custom event that UI components can listen for
      window.dispatchEvent(new CustomEvent('collaboration-status-change', { 
        detail: { status: event.status } 
      }));
    });
    
    // Handle connection errors
    websocketProvider.on('connection-error', error => {
      console.error('Collaboration connection error:', error);
      window.dispatchEvent(new CustomEvent('collaboration-error', { 
        detail: { error: error } 
      }));
    });
    
    // Handle connection close
    websocketProvider.on('connection-close', event => {
      console.log('Collaboration connection closed:', event);
      // Try to reconnect if the connection was closed unexpectedly
      if (event.code !== 1000) {
        console.log('Attempting to reconnect...');
        setTimeout(() => websocketProvider.connect(), 3000);
      }
    });
    
    // Make the collaboration objects available to the application
    if (app) {
      app.ydoc = ydoc;
      app.websocketProvider = websocketProvider;
      app.awareness = websocketProvider.awareness;
    }
    
    // Return the collaboration objects for use elsewhere
    return {
      ydoc,
      websocketProvider,
      awareness: websocketProvider.awareness
    };
  } catch (error) {
    console.error('Failed to initialize collaborative editing:', error);
    window.dispatchEvent(new CustomEvent('collaboration-initialization-failed', { 
      detail: { error: error } 
    }));
    return null;
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

  const app = new NotebookApp({
    pluginRegistry,
    serviceManager,
    mimeExtensions,
    availablePlugins
  });

  // Expose global app instance when in dev mode or when toggled explicitly.
  const exposeAppInBrowser =
    (PageConfig.getOption('exposeAppInBrowser') || '').toLowerCase() === 'true';

  if (exposeAppInBrowser) {
    window.jupyterapp = app;
  }
  
  // Initialize collaborative editing after app is created but before it starts
  const collaborationObjects = initCollaboration(app);
  
  // If collaboration is enabled and initialized successfully, make it available globally
  // for extension components to access
  if (collaborationObjects) {
    // Register collaboration objects with the application
    app.registerCollaborationObjects = () => {
      return collaborationObjects;
    };
    
    // Make collaboration objects available to extensions through a global registry
    window._JUPYTER_COLLABORATION = collaborationObjects;
    
    console.log('Collaborative editing initialized successfully');
    
    // Discover and register collaborative UI components
    try {
      // Look for collaboration UI components in the federated extensions
      const collaborationUIComponents = availablePlugins.filter(plugin => 
        plugin.id.includes('collaboration') || 
        (plugin.description && plugin.description.includes('collaboration'))
      );
      
      if (collaborationUIComponents.length > 0) {
        console.log(`Found ${collaborationUIComponents.length} collaboration UI components`);
      } else {
        console.log('No collaboration UI components found in available plugins');
      }
    } catch (error) {
      console.error('Error discovering collaboration UI components:', error);
    }
  }

  await app.start();
}

window.addEventListener('load', main);

// Handle collaboration cleanup when the window is closed or refreshed
window.addEventListener('beforeunload', () => {
  // Clean up Yjs document and WebSocket connection if they exist
  if (window._JUPYTER_COLLABORATION) {
    try {
      const { websocketProvider, ydoc } = window._JUPYTER_COLLABORATION;
      if (websocketProvider) {
        websocketProvider.disconnect();
      }
      if (ydoc) {
        ydoc.destroy();
      }
      console.log('Collaboration resources cleaned up');
    } catch (error) {
      console.error('Error cleaning up collaboration resources:', error);
    }
  }
});