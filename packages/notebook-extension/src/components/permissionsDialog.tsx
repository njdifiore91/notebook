// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import * as React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { ReactWidget } from '@jupyterlab/ui-components';
import { showDialog, Dialog } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

/**
 * Interface for a user with permissions
 */
interface ICollaborator {
  /**
   * Unique identifier for the user
   */
  id: string;

  /**
   * Display name of the user
   */
  displayName: string;

  /**
   * Email address of the user (optional)
   */
  email?: string;

  /**
   * URL to the user's avatar image (optional)
   */
  avatarUrl?: string;

  /**
   * Current permission level for the user
   */
  permission: PermissionLevel;
}

/**
 * Permission levels for collaborative notebook access
 */
enum PermissionLevel {
  /**
   * Can only view the notebook content
   */
  VIEW = 'view',

  /**
   * Can view and add comments, but not edit content
   */
  COMMENT = 'comment',

  /**
   * Can view, comment, and edit notebook content
   */
  EDIT = 'edit',

  /**
   * Can view, comment, edit, and manage permissions
   */
  ADMIN = 'admin',

  /**
   * Has complete control over the notebook
   */
  OWNER = 'owner'
}

/**
 * Interface for the permissions service
 */
export interface IPermissionsService {
  /**
   * Get all collaborators for the current notebook
   */
  getCollaborators(): Promise<ICollaborator[]>;

  /**
   * Update a collaborator's permission level
   * 
   * @param userId - The ID of the user to update
   * @param permission - The new permission level
   */
  updatePermission(userId: string, permission: PermissionLevel): Promise<void>;

  /**
   * Add a new collaborator to the notebook
   * 
   * @param userIdentifier - Email or username to identify the user
   * @param permission - The permission level to grant
   */
  addCollaborator(userIdentifier: string, permission: PermissionLevel): Promise<ICollaborator>;

  /**
   * Remove a collaborator from the notebook
   * 
   * @param userId - The ID of the user to remove
   */
  removeCollaborator(userId: string): Promise<void>;

  /**
   * Get the current user's permission level
   */
  getCurrentUserPermission(): Promise<PermissionLevel>;

  /**
   * Check if the current user can modify permissions
   */
  canManagePermissions(): Promise<boolean>;
}

/**
 * Props for the PermissionsDialog component
 */
interface IPermissionsDialogProps {
  /**
   * The permissions service instance
   */
  permissionsService: IPermissionsService;

  /**
   * The translator instance
   */
  translator?: ITranslator;

  /**
   * Callback when the dialog is closed
   */
  onClose?: () => void;
}

/**
 * A React component for managing permissions in collaborative notebooks
 */
function PermissionsDialog(props: IPermissionsDialogProps): JSX.Element {
  const { permissionsService, onClose } = props;
  const translator = props.translator || nullTranslator;
  const trans = translator.load('notebook');

  // State for collaborators list
  const [collaborators, setCollaborators] = useState<ICollaborator[]>([]);
  
  // State for new collaborator input
  const [newCollaborator, setNewCollaborator] = useState('');
  
  // State for new collaborator permission
  const [newPermission, setNewPermission] = useState<PermissionLevel>(PermissionLevel.VIEW);
  
  // State for loading indicators
  const [isLoading, setIsLoading] = useState(true);
  
  // State for error messages
  const [errorMessage, setErrorMessage] = useState('');
  
  // State for current user's permission level
  const [currentUserPermission, setCurrentUserPermission] = useState<PermissionLevel | null>(null);
  
  // State for whether current user can manage permissions
  const [canManage, setCanManage] = useState(false);

  // Load collaborators on component mount
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);
        const [collabs, userPerm, canManagePerms] = await Promise.all([
          permissionsService.getCollaborators(),
          permissionsService.getCurrentUserPermission(),
          permissionsService.canManagePermissions()
        ]);
        setCollaborators(collabs);
        setCurrentUserPermission(userPerm);
        setCanManage(canManagePerms);
        setErrorMessage('');
      } catch (error) {
        console.error('Failed to load collaborators:', error);
        setErrorMessage(trans.__('Failed to load collaborators. Please try again.'));
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [permissionsService, trans]);

  // Handle permission change for a collaborator
  const handlePermissionChange = useCallback(async (userId: string, newPermission: PermissionLevel) => {
    try {
      await permissionsService.updatePermission(userId, newPermission);
      
      // Update the collaborators list with the new permission
      setCollaborators(prevCollaborators => 
        prevCollaborators.map(collab => 
          collab.id === userId ? { ...collab, permission: newPermission } : collab
        )
      );
      setErrorMessage('');
    } catch (error) {
      console.error('Failed to update permission:', error);
      setErrorMessage(trans.__('Failed to update permission. Please try again.'));
    }
  }, [permissionsService, trans]);

  // Handle adding a new collaborator
  const handleAddCollaborator = useCallback(async () => {
    if (!newCollaborator.trim()) {
      setErrorMessage(trans.__('Please enter a valid email or username.'));
      return;
    }

    try {
      const collaborator = await permissionsService.addCollaborator(
        newCollaborator.trim(),
        newPermission
      );
      
      // Add the new collaborator to the list
      setCollaborators(prevCollaborators => [...prevCollaborators, collaborator]);
      
      // Reset the input field
      setNewCollaborator('');
      setErrorMessage('');
    } catch (error) {
      console.error('Failed to add collaborator:', error);
      setErrorMessage(trans.__('Failed to add collaborator. Please check the email or username and try again.'));
    }
  }, [newCollaborator, newPermission, permissionsService, trans]);

  // Handle removing a collaborator
  const handleRemoveCollaborator = useCallback(async (userId: string) => {
    try {
      await permissionsService.removeCollaborator(userId);
      
      // Remove the collaborator from the list
      setCollaborators(prevCollaborators => 
        prevCollaborators.filter(collab => collab.id !== userId)
      );
      setErrorMessage('');
    } catch (error) {
      console.error('Failed to remove collaborator:', error);
      setErrorMessage(trans.__('Failed to remove collaborator. Please try again.'));
    }
  }, [permissionsService, trans]);

  // Get human-readable permission label
  const getPermissionLabel = (permission: PermissionLevel): string => {
    switch (permission) {
      case PermissionLevel.VIEW:
        return trans.__('View only');
      case PermissionLevel.COMMENT:
        return trans.__('Can comment');
      case PermissionLevel.EDIT:
        return trans.__('Can edit');
      case PermissionLevel.ADMIN:
        return trans.__('Admin');
      case PermissionLevel.OWNER:
        return trans.__('Owner');
      default:
        return trans.__('Unknown');
    }
  };

  // Render permission options dropdown
  const renderPermissionOptions = (collaborator: ICollaborator) => {
    // If user can't manage permissions or is viewing their own permissions and they're the owner,
    // just show the current permission level as text
    const isCurrentUser = currentUserPermission === PermissionLevel.OWNER && 
                         collaborator.permission === PermissionLevel.OWNER;
    
    if (!canManage || isCurrentUser) {
      return <span>{getPermissionLabel(collaborator.permission)}</span>;
    }

    // Otherwise, show a dropdown to change permissions
    return (
      <select
        value={collaborator.permission}
        onChange={(e) => handlePermissionChange(collaborator.id, e.target.value as PermissionLevel)}
        aria-label={trans.__('Change permission level')}
        className="jp-mod-styled jp-PermissionsDialog-select"
      >
        <option value={PermissionLevel.VIEW}>{getPermissionLabel(PermissionLevel.VIEW)}</option>
        <option value={PermissionLevel.COMMENT}>{getPermissionLabel(PermissionLevel.COMMENT)}</option>
        <option value={PermissionLevel.EDIT}>{getPermissionLabel(PermissionLevel.EDIT)}</option>
        <option value={PermissionLevel.ADMIN}>{getPermissionLabel(PermissionLevel.ADMIN)}</option>
        {/* Only show Owner option for admins */}
        {currentUserPermission === PermissionLevel.OWNER && (
          <option value={PermissionLevel.OWNER}>{getPermissionLabel(PermissionLevel.OWNER)}</option>
        )}
      </select>
    );
  };

  return (
    <div className="jp-PermissionsDialog">
      <div className="jp-PermissionsDialog-header">
        <h2>{trans.__('Manage Access')}</h2>
        <p className="jp-PermissionsDialog-description">
          {trans.__('Control who can view, comment on, or edit this notebook.')}
        </p>
      </div>

      {errorMessage && (
        <div className="jp-PermissionsDialog-error" role="alert">
          {errorMessage}
        </div>
      )}

      {isLoading ? (
        <div className="jp-PermissionsDialog-loading">
          <div className="jp-Spinner"/>
          <span>{trans.__('Loading collaborators...')}</span>
        </div>
      ) : (
        <>
          {/* Current collaborators list */}
          <div className="jp-PermissionsDialog-collaborators">
            <h3>{trans.__('Collaborators')}</h3>
            {collaborators.length === 0 ? (
              <p className="jp-PermissionsDialog-empty">
                {trans.__('No collaborators yet. Add people to collaborate on this notebook.')}
              </p>
            ) : (
              <ul className="jp-PermissionsDialog-list" role="list">
                {collaborators.map(collaborator => (
                  <li key={collaborator.id} className="jp-PermissionsDialog-collaborator">
                    <div className="jp-PermissionsDialog-collaboratorInfo">
                      <div className="jp-PermissionsDialog-avatar">
                        {collaborator.avatarUrl ? (
                          <img 
                            src={collaborator.avatarUrl} 
                            alt="" 
                            aria-hidden="true"
                          />
                        ) : (
                          <div className="jp-PermissionsDialog-avatarFallback">
                            {collaborator.displayName.charAt(0).toUpperCase()}
                          </div>
                        )}
                      </div>
                      <div className="jp-PermissionsDialog-userDetails">
                        <span className="jp-PermissionsDialog-userName">
                          {collaborator.displayName}
                        </span>
                        {collaborator.email && (
                          <span className="jp-PermissionsDialog-userEmail">
                            {collaborator.email}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="jp-PermissionsDialog-collaboratorActions">
                      <div className="jp-PermissionsDialog-permission">
                        {renderPermissionOptions(collaborator)}
                      </div>
                      {canManage && collaborator.permission !== PermissionLevel.OWNER && (
                        <button 
                          className="jp-PermissionsDialog-removeButton jp-mod-styled"
                          onClick={() => handleRemoveCollaborator(collaborator.id)}
                          aria-label={trans.__('Remove collaborator')}
                          title={trans.__('Remove collaborator')}
                        >
                          <span className="jp-PermissionsDialog-removeIcon" aria-hidden="true">×</span>
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Add new collaborator form */}
          {canManage && (
            <div className="jp-PermissionsDialog-addForm">
              <h3>{trans.__('Add people')}</h3>
              <div className="jp-PermissionsDialog-inputGroup">
                <input
                  type="text"
                  value={newCollaborator}
                  onChange={(e) => setNewCollaborator(e.target.value)}
                  placeholder={trans.__('Email or username')}
                  aria-label={trans.__('Email or username')}
                  className="jp-mod-styled jp-PermissionsDialog-input"
                />
                <select
                  value={newPermission}
                  onChange={(e) => setNewPermission(e.target.value as PermissionLevel)}
                  aria-label={trans.__('Permission level')}
                  className="jp-mod-styled jp-PermissionsDialog-select"
                >
                  <option value={PermissionLevel.VIEW}>{getPermissionLabel(PermissionLevel.VIEW)}</option>
                  <option value={PermissionLevel.COMMENT}>{getPermissionLabel(PermissionLevel.COMMENT)}</option>
                  <option value={PermissionLevel.EDIT}>{getPermissionLabel(PermissionLevel.EDIT)}</option>
                  <option value={PermissionLevel.ADMIN}>{getPermissionLabel(PermissionLevel.ADMIN)}</option>
                </select>
                <button 
                  className="jp-mod-styled jp-mod-primary jp-PermissionsDialog-addButton"
                  onClick={handleAddCollaborator}
                  disabled={!newCollaborator.trim()}
                  aria-label={trans.__('Add collaborator')}
                >
                  {trans.__('Add')}
                </button>
              </div>
            </div>
          )}

          {/* Help text */}
          <div className="jp-PermissionsDialog-help">
            <h3>{trans.__('Access levels')}</h3>
            <ul className="jp-PermissionsDialog-helpList">
              <li>
                <strong>{getPermissionLabel(PermissionLevel.VIEW)}</strong>: {trans.__('Can view but not edit or comment on the notebook.')}
              </li>
              <li>
                <strong>{getPermissionLabel(PermissionLevel.COMMENT)}</strong>: {trans.__('Can view and add comments, but cannot edit the notebook content.')}
              </li>
              <li>
                <strong>{getPermissionLabel(PermissionLevel.EDIT)}</strong>: {trans.__('Can view, comment, and edit the notebook content.')}
              </li>
              <li>
                <strong>{getPermissionLabel(PermissionLevel.ADMIN)}</strong>: {trans.__('Can view, comment, edit, and manage access permissions.')}
              </li>
              <li>
                <strong>{getPermissionLabel(PermissionLevel.OWNER)}</strong>: {trans.__('Has complete control over the notebook.')}
              </li>
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * A namespace for PermissionsDialog statics.
 */
export namespace PermissionsDialog {
  /**
   * Show the permissions dialog.
   *
   * @param permissionsService - The permissions service instance
   * @param translator - The translator instance
   * @returns A promise that resolves with whether the dialog was accepted.
   */
  export function showDialog(
    permissionsService: IPermissionsService,
    translator?: ITranslator
  ): Promise<Dialog.IResult<void>> {
    translator = translator || nullTranslator;
    const trans = translator.load('notebook');

    // Create the dialog body as a ReactWidget
    const body = ReactWidget.create(
      <PermissionsDialog 
        permissionsService={permissionsService} 
        translator={translator} 
      />
    );
    body.addClass('jp-PermissionsDialog-content');

    return Dialog.show({
      title: trans.__('Manage Access'),
      body,
      buttons: [
        Dialog.cancelButton({ label: trans.__('Close') })
      ],
    });
  }
}