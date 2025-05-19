// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { URLExt } from '@jupyterlab/coreutils';

import { CollaborationPermission, INotebookPathOpener } from './tokens';

/**
 * A class to open paths in new browser tabs in the Notebook application.
 */
class DefaultNotebookPathOpener implements INotebookPathOpener {
  /**
   * Open a path in a new browser tab.
   */
  open(options: INotebookPathOpener.IOpenOptions): WindowProxy | null {
    const { 
      prefix, 
      path, 
      searchParams, 
      target, 
      features,
      collaborationSessionId,
      startCollaboration,
      collaborationPermission 
    } = options;
    
    const url = new URL(
      URLExt.join(prefix, path ?? ''),
      window.location.origin
    );
    
    // Create a new URLSearchParams if none was provided
    const params = searchParams ? new URLSearchParams(searchParams) : new URLSearchParams();
    
    // Add collaboration-specific URL parameters if provided
    if (collaborationSessionId) {
      params.set('collaboration', collaborationSessionId);
    } else if (startCollaboration) {
      params.set('startCollaboration', 'true');
    }
    
    // Add permission parameter if provided
    if (collaborationPermission) {
      params.set('collaborationPermission', collaborationPermission);
    }
    
    // Set the search parameters on the URL
    url.search = params.toString();
    
    return window.open(url, target, features);
  }
}

export const defaultNotebookPathOpener = new DefaultNotebookPathOpener();
