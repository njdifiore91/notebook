import { ReactWidget } from '@jupyterlab/apputils';

import { Notebook, NotebookActions } from '@jupyterlab/notebook';

import { ITranslator } from '@jupyterlab/translation';

import React, { useEffect, useState } from 'react';

/**
 * Interface for the permissions service that handles collaboration permissions
 */
export interface IPermissionsService {
  /**
   * Check if the user has permission to perform an action on a resource
   * 
   * @param action - The action to check permission for
   * @param resourceId - The ID of the resource to check permission for
   * @returns A promise that resolves to true if the user has permission, false otherwise
   */
  hasPermission(action: string, resourceId: string): Promise<boolean>;

  /**
   * Get the current user's role for a specific resource
   * 
   * @param resourceId - The ID of the resource to get the role for
   * @returns A promise that resolves to the user's role or null if not in a collaborative session
   */
  getUserRole(resourceId: string): Promise<string | null>;

  /**
   * Check if the notebook is in a collaborative session
   * 
   * @param resourceId - The ID of the resource to check
   * @returns A promise that resolves to true if the notebook is in a collaborative session
   */
  isCollaborative(resourceId: string): Promise<boolean>;
}

/**
 * Check if a notebook is trusted
 * @param notebook The notebook to check
 * @param permissionsService Optional permissions service for collaborative trust checking
 * @returns true if the notebook is trusted, false otherwise
 */
const isTrusted = async (
  notebook: Notebook,
  permissionsService?: IPermissionsService
): Promise<boolean> => {
  // Check local trust status
  const model = notebook.model;
  if (!model) {
    return false;
  }
  const cells = Array.from(model.cells);
  let total = 0;
  let trusted = 0;

  for (const currentCell of cells) {
    if (currentCell.type !== 'code') {
      continue;
    }
    total++;
    if (currentCell.trusted) {
      trusted++;
    }
  }

  const localTrusted = trusted === total;

  // If no permissions service or not in a collaborative session, return local trust status
  if (!permissionsService) {
    return localTrusted;
  }

  try {
    // Check if this is a collaborative notebook
    const notebookId = notebook.context?.path || '';
    const isCollaborative = await permissionsService.isCollaborative(notebookId);
    
    if (!isCollaborative) {
      return localTrusted;
    }

    // In collaborative mode, check if the user has permission to trust the notebook
    const canTrust = await permissionsService.hasPermission('trust', notebookId);
    
    // If the user doesn't have permission to trust, the notebook is only trusted
    // if it's already trusted locally
    if (!canTrust) {
      return localTrusted;
    }

    // If the user has permission to trust, the notebook is trusted
    return true;
  } catch (error) {
    console.error('Error checking collaborative trust status:', error);
    // Fall back to local trust status in case of errors
    return localTrusted;
  }
};

/**
 * Trust status type for the notebook
 */
type TrustStatus = {
  trusted: boolean;
  collaborative: boolean;
  canTrust: boolean;
};

/**
 * A React component to display the Trusted badge in the menu bar.
 * @param notebook The Notebook
 * @param translator The Translation service
 * @param permissionsService Optional permissions service for collaborative trust checking
 */
const TrustedButton = ({
  notebook,
  translator,
  permissionsService
}: {
  notebook: Notebook;
  translator: ITranslator;
  permissionsService?: IPermissionsService;
}): JSX.Element => {
  const trans = translator.load('notebook');
  const [trustStatus, setTrustStatus] = useState<TrustStatus>({
    trusted: false,
    collaborative: false,
    canTrust: true
  });

  const checkTrust = async () => {
    // Check local trust status
    const localTrusted = await isTrusted(notebook);
    
    // Default trust status (non-collaborative)
    let status: TrustStatus = {
      trusted: localTrusted,
      collaborative: false,
      canTrust: true
    };

    // If permissions service is available, check collaborative status
    if (permissionsService) {
      try {
        const notebookId = notebook.context?.path || '';
        const isCollaborative = await permissionsService.isCollaborative(notebookId);
        
        if (isCollaborative) {
          const canTrust = await permissionsService.hasPermission('trust', notebookId);
          const userRole = await permissionsService.getUserRole(notebookId);
          
          status = {
            trusted: localTrusted,
            collaborative: true,
            canTrust: canTrust
          };
        }
      } catch (error) {
        console.error('Error checking collaborative status:', error);
      }
    }

    setTrustStatus(status);
  };

  const trust = async () => {
    // Only attempt to trust if the user has permission
    if (trustStatus.canTrust) {
      await NotebookActions.trust(notebook, translator);
      checkTrust();
    }
  };

  useEffect(() => {
    notebook.modelContentChanged.connect(checkTrust);
    notebook.activeCellChanged.connect(checkTrust);
    checkTrust();
    return () => {
      notebook.modelContentChanged.disconnect(checkTrust);
      notebook.activeCellChanged.disconnect(checkTrust);
    };
  }, [permissionsService]);

  // Determine button style and title based on trust status
  let buttonStyle = !trustStatus.trusted ? { cursor: 'pointer' } : { cursor: 'help' };
  let buttonTitle = trustStatus.trusted
    ? trans.__('JavaScript enabled for notebook display')
    : trans.__('JavaScript disabled for notebook display');
  
  // If in collaborative mode and can't trust, show different cursor and title
  if (trustStatus.collaborative && !trustStatus.canTrust) {
    buttonStyle = { cursor: 'not-allowed' };
    buttonTitle = trustStatus.trusted
      ? trans.__('Notebook is trusted (collaborative mode)')
      : trans.__('Insufficient permissions to trust this notebook in collaborative mode');
  }

  // Determine button text based on trust and collaboration status
  let buttonText = trustStatus.trusted ? trans.__('Trusted') : trans.__('Not Trusted');
  if (trustStatus.collaborative) {
    buttonText = trustStatus.trusted 
      ? trans.__('Trusted (Collaborative)') 
      : trans.__('Not Trusted (Collaborative)');
  }

  return (
    <button
      className={'jp-NotebookTrustedStatus'}
      style={buttonStyle}
      onClick={() => !trustStatus.trusted && trustStatus.canTrust && trust()}
      title={buttonTitle}
    >
      {buttonText}
    </button>
  );
};

/**
 * A namespace for TrustedComponent static methods.
 */
export namespace TrustedComponent {
  /**
   * Create a new TrustedComponent
   *
   * @param notebook The notebook
   * @param translator The translator
   * @param permissionsService Optional permissions service for collaborative trust checking
   */
  export const create = ({
    notebook,
    translator,
    permissionsService
  }: {
    notebook: Notebook;
    translator: ITranslator;
    permissionsService?: IPermissionsService;
  }): ReactWidget => {
    return ReactWidget.create(
      <TrustedButton 
        notebook={notebook} 
        translator={translator} 
        permissionsService={permissionsService} 
      />
    );
  };
}