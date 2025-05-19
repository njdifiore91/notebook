import { ReactWidget } from '@jupyterlab/apputils';

import { Notebook, NotebookActions } from '@jupyterlab/notebook';

import { ITranslator } from '@jupyterlab/translation';

import React, { useEffect, useState } from 'react';

import { IPermissionsService } from './index';

/**
 * Check if a notebook is trusted
 * @param notebook The notebook to check
 * @param permissionsService Optional permissions service for collaboration trust checks
 * @returns true if the notebook is trusted, false otherwise
 */
const isTrusted = (notebook: Notebook, permissionsService?: IPermissionsService | null): boolean => {
  // First check local trust status
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

  // If no permissions service or not enabled, just return local trust status
  if (!permissionsService || !permissionsService.enabled) {
    return localTrusted;
  }

  // For collaborative notebooks, also check if the user has appropriate permissions
  // A notebook is considered trusted in collaborative mode if:
  // 1. The local notebook is trusted AND
  // 2. The user has at least 'view' permission in the collaborative session
  return localTrusted && permissionsService.hasPermission('view');
};

/**
 * A React component to display the Trusted badge in the menu bar.
 * @param notebook The Notebook
 * @param translator The Translation service
 * @param permissionsService Optional permissions service for collaboration features
 */
const TrustedButton = ({
  notebook,
  translator,
  permissionsService,
}: {
  notebook: Notebook;
  translator: ITranslator;
  permissionsService?: IPermissionsService | null;
}): JSX.Element => {
  const trans = translator.load('notebook');
  const [trusted, setTrusted] = useState(isTrusted(notebook, permissionsService));
  const [isCollaborative, setIsCollaborative] = useState(
    permissionsService?.enabled ?? false
  );

  const checkTrust = () => {
    const v = isTrusted(notebook, permissionsService);
    setTrusted(v);
    setIsCollaborative(permissionsService?.enabled ?? false);
  };

  const trust = async () => {
    // Only allow trusting if user has appropriate permissions in collaborative mode
    if (isCollaborative && permissionsService) {
      // Check if user has edit permission before allowing trust action
      if (!permissionsService.hasPermission('edit')) {
        // If user doesn't have edit permission, don't allow trusting
        return;
      }
    }
    
    await NotebookActions.trust(notebook, translator);
    checkTrust();
  };

  useEffect(() => {
    notebook.modelContentChanged.connect(checkTrust);
    notebook.activeCellChanged.connect(checkTrust);
    
    // If using collaboration, also check when permissions change
    if (permissionsService) {
      // We would ideally connect to a signal from the permissions service here
      // For now, we'll just check periodically
      const interval = setInterval(checkTrust, 5000);
      return () => {
        notebook.modelContentChanged.disconnect(checkTrust);
        notebook.activeCellChanged.disconnect(checkTrust);
        clearInterval(interval);
      };
    }
    
    checkTrust();
    return () => {
      notebook.modelContentChanged.disconnect(checkTrust);
      notebook.activeCellChanged.disconnect(checkTrust);
    };
  }, [permissionsService]);

  // Determine button title based on trust status and collaboration mode
  let buttonTitle = '';
  if (isCollaborative) {
    if (trusted) {
      buttonTitle = trans.__('JavaScript enabled for notebook display (Collaborative Mode)');
    } else {
      buttonTitle = trans.__('JavaScript disabled for notebook display (Collaborative Mode)');
    }
  } else {
    if (trusted) {
      buttonTitle = trans.__('JavaScript enabled for notebook display');
    } else {
      buttonTitle = trans.__('JavaScript disabled for notebook display');
    }
  }

  // Determine if the button should be clickable
  // In collaborative mode, only users with edit permission can change trust status
  const canChangeTrust = !isCollaborative || 
    (permissionsService && permissionsService.hasPermission('edit'));

  // Add a special class for collaborative mode
  const collaborativeClass = isCollaborative ? 'jp-NotebookTrustedStatus-collaborative' : '';

  return (
    <button
      className={`jp-NotebookTrustedStatus ${collaborativeClass}`}
      style={!trusted && canChangeTrust ? { cursor: 'pointer' } : { cursor: 'help' }}
      onClick={() => !trusted && canChangeTrust && trust()}
      title={buttonTitle}
    >
      {trusted ? trans.__('Trusted') : trans.__('Not Trusted')}
      {isCollaborative && <span className="jp-NotebookTrustedStatus-collaborativeIcon" title={trans.__('Collaborative Mode')}></span>}
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
   * @param permissionsService Optional permissions service for collaboration features
   */
  export const create = ({
    notebook,
    translator,
    permissionsService,
  }: {
    notebook: Notebook;
    translator: ITranslator;
    permissionsService?: IPermissionsService | null;
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