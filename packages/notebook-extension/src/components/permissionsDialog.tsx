// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useCallback } from 'react';
import { Dialog, showDialog } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { ReactWidget } from '@jupyterlab/apputils';
import { IPermissionsService, ICollaborationService } from '../tokens';
import { Button, Select, Checkbox, Avatar } from '@jupyterlab/ui-components';

/**
 * Interface for a user with permissions
 */
interface IUserPermission {
  /**
   * User ID (typically from JupyterHub)
   */
  userId: string;

  /**
   * Display name of the user
   */
  displayName: string;

  /**
   * Email address of the user
   */
  email?: string;

  /**
   * Avatar URL for the user
   */
  avatarUrl?: string;

  /**
   * Current role assigned to the user
   */
  role: 'viewer' | 'commenter' | 'editor' | 'admin' | 'owner';
}

/**
 * Props for the PermissionsDialog component
 */
interface IPermissionsDialogProps {
  /**
   * The permissions service
   */
  permissionsService: IPermissionsService;

  /**
   * The collaboration service
   */
  collaborationService: ICollaborationService;

  /**
   * The translator
   */
  translator?: ITranslator;

  /**
   * Callback when the dialog is closed
   */
  onClose?: () => void;
}

/**
 * A React component for managing user permissions in collaborative notebooks
 */
export function PermissionsDialog(props: IPermissionsDialogProps): JSX.Element {
  const {
    permissionsService,
    collaborationService,
    translator = nullTranslator,
    onClose
  } = props;

  const trans = translator.load('notebook');

  // State for users and their permissions
  const [users, setUsers] = useState<IUserPermission[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [newUserEmail, setNewUserEmail] = useState<string>('');
  const [currentUser, setCurrentUser] = useState<IUserPermission | null>(null);

  // Load users and their permissions
  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const userPermissions = await permissionsService.getUserPermissions();
      setUsers(userPermissions);
      
      // Get current user information
      const currentUserInfo = await collaborationService.getCurrentUser();
      if (currentUserInfo) {
        const currentUserPermission = userPermissions.find(
          user => user.userId === currentUserInfo.userId
        );
        setCurrentUser(currentUserPermission || null);
      }
    } catch (err) {
      console.error('Failed to load user permissions:', err);
      setError(trans.__('Failed to load user permissions. Please try again.'));
    } finally {
      setLoading(false);
    }
  }, [permissionsService, collaborationService, trans]);

  // Load users on component mount
  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // Handle role change for a user
  const handleRoleChange = async (
    userId: string,
    newRole: 'viewer' | 'commenter' | 'editor' | 'admin' | 'owner'
  ) => {
    try {
      await permissionsService.setUserRole(userId, newRole);
      setUsers(prevUsers =>
        prevUsers.map(user =>
          user.userId === userId ? { ...user, role: newRole } : user
        )
      );
    } catch (err) {
      console.error('Failed to update user role:', err);
      setError(trans.__('Failed to update user role. Please try again.'));
    }
  };

  // Handle adding a new user
  const handleAddUser = async () => {
    if (!newUserEmail) {
      return;
    }

    try {
      await permissionsService.addUser(newUserEmail, 'viewer');
      setNewUserEmail('');
      loadUsers(); // Reload the user list
    } catch (err) {
      console.error('Failed to add user:', err);
      setError(trans.__('Failed to add user. Please try again.'));
    }
  };

  // Handle removing a user
  const handleRemoveUser = async (userId: string) => {
    try {
      await permissionsService.removeUser(userId);
      setUsers(prevUsers => prevUsers.filter(user => user.userId !== userId));
    } catch (err) {
      console.error('Failed to remove user:', err);
      setError(trans.__('Failed to remove user. Please try again.'));
    }
  };

  // Check if current user can modify permissions
  const canModifyPermissions = currentUser?.role === 'admin' || currentUser?.role === 'owner';

  // Render role selection dropdown
  const renderRoleSelector = (user: IUserPermission) => {
    const isCurrentUser = currentUser?.userId === user.userId;
    const isOwner = user.role === 'owner';
    
    // Owners can't change their own role and non-admins can't change roles
    const disabled = isOwner || (isCurrentUser && isOwner) || !canModifyPermissions;

    return (
      <Select
        aria-label={trans.__('Select role for %1', user.displayName)}
        className="jp-PermissionsDialog-roleSelect"
        disabled={disabled}
        value={user.role}
        onChange={e => handleRoleChange(user.userId, e.target.value as any)}
      >
        <option value="viewer">{trans.__('Viewer')}</option>
        <option value="commenter">{trans.__('Commenter')}</option>
        <option value="editor">{trans.__('Editor')}</option>
        <option value="admin">{trans.__('Admin')}</option>
        {isOwner && <option value="owner">{trans.__('Owner')}</option>}
      </Select>
    );
  };

  return (
    <div className="jp-PermissionsDialog">
      <div className="jp-PermissionsDialog-header">
        <h2>{trans.__('Manage Permissions')}</h2>
        {error && <div className="jp-PermissionsDialog-error">{error}</div>}
      </div>

      {loading ? (
        <div className="jp-PermissionsDialog-loading">
          {trans.__('Loading user permissions...')}
        </div>
      ) : (
        <>
          <div className="jp-PermissionsDialog-description">
            <p>
              {trans.__(
                'Control who can view, comment on, or edit this notebook. Only admins and the owner can modify permissions.'
              )}
            </p>
          </div>

          <div className="jp-PermissionsDialog-roles">
            <h3>{trans.__('Role Descriptions')}</h3>
            <ul>
              <li>
                <strong>{trans.__('Viewer')}:</strong>{' '}
                {trans.__('Can view notebook content but cannot edit or comment.')}
              </li>
              <li>
                <strong>{trans.__('Commenter')}:</strong>{' '}
                {trans.__('Can view and add comments but cannot edit content.')}
              </li>
              <li>
                <strong>{trans.__('Editor')}:</strong>{' '}
                {trans.__('Can view, comment, and edit notebook content.')}
              </li>
              <li>
                <strong>{trans.__('Admin')}:</strong>{' '}
                {trans.__('Can edit content and manage user permissions.')}
              </li>
              <li>
                <strong>{trans.__('Owner')}:</strong>{' '}
                {trans.__('Has full control over the notebook and can transfer ownership.')}
              </li>
            </ul>
          </div>

          <div className="jp-PermissionsDialog-userList">
            <h3>{trans.__('Users')}</h3>
            <table aria-label={trans.__('User permissions table')}>
              <thead>
                <tr>
                  <th scope="col">{trans.__('User')}</th>
                  <th scope="col">{trans.__('Role')}</th>
                  <th scope="col">{trans.__('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {users.map(user => (
                  <tr key={user.userId}>
                    <td className="jp-PermissionsDialog-userCell">
                      <div className="jp-PermissionsDialog-userInfo">
                        <Avatar
                          src={user.avatarUrl}
                          alt={user.displayName}
                          className="jp-PermissionsDialog-avatar"
                        />
                        <div>
                          <div className="jp-PermissionsDialog-userName">
                            {user.displayName}
                            {currentUser?.userId === user.userId && (
                              <span className="jp-PermissionsDialog-currentUser">
                                {trans.__(" (You)")}
                              </span>
                            )}
                          </div>
                          {user.email && (
                            <div className="jp-PermissionsDialog-userEmail">
                              {user.email}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>{renderRoleSelector(user)}</td>
                    <td>
                      {user.role !== 'owner' && canModifyPermissions && (
                        <Button
                          className="jp-PermissionsDialog-removeButton"
                          onClick={() => handleRemoveUser(user.userId)}
                          aria-label={trans.__('Remove %1', user.displayName)}
                        >
                          {trans.__('Remove')}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {canModifyPermissions && (
            <div className="jp-PermissionsDialog-addUser">
              <h3>{trans.__('Add User')}</h3>
              <div className="jp-PermissionsDialog-addUserForm">
                <input
                  type="text"
                  placeholder={trans.__('Enter email address')}
                  value={newUserEmail}
                  onChange={e => setNewUserEmail(e.target.value)}
                  aria-label={trans.__('Email address for new user')}
                  className="jp-PermissionsDialog-emailInput"
                />
                <Button
                  className="jp-PermissionsDialog-addButton"
                  onClick={handleAddUser}
                  disabled={!newUserEmail}
                  aria-label={trans.__('Add user')}
                >
                  {trans.__('Add')}
                </Button>
              </div>
              <p className="jp-PermissionsDialog-addUserHelp">
                {trans.__(
                  'Users must have a JupyterHub account to be added. They will receive access after you add them.'
                )}
              </p>
            </div>
          )}

          <div className="jp-PermissionsDialog-actions">
            <Button
              className="jp-PermissionsDialog-closeButton"
              onClick={onClose}
              aria-label={trans.__('Close dialog')}
            >
              {trans.__('Close')}
            </Button>
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
   * @param permissionsService - The permissions service
   * @param collaborationService - The collaboration service
   * @param translator - The translator
   * @returns A promise that resolves with whether the dialog was accepted.
   */
  export async function showDialog(
    permissionsService: IPermissionsService,
    collaborationService: ICollaborationService,
    translator: ITranslator = nullTranslator
  ): Promise<Dialog.IResult<void>> {
    const trans = translator.load('notebook');
    const dialog = new Dialog({
      title: trans.__('Manage Permissions'),
      body: ReactWidget.create(
        <PermissionsDialog
          permissionsService={permissionsService}
          collaborationService={collaborationService}
          translator={translator}
          onClose={() => dialog.resolve()}
        />
      ),
      buttons: [] // We'll handle buttons in the component itself
    });

    return dialog.launch();
  }
}