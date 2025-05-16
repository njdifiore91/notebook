// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useEffect, useState } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { Dialog, showDialog } from '@jupyterlab/apputils';
import { NotebookPanel } from '@jupyterlab/notebook';
import {
  IPermissionManager,
  DocumentRole,
  CellPermission,
  IUserPermission,
  ICellPermission
} from '@jupyterlab/notebook/lib/collab/permissions';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Time } from '@jupyterlab/coreutils';

/**
 * Props for the PermissionsDialog component.
 */
export interface IPermissionsDialogProps {
  /**
   * The permission manager instance.
   */
  permissionManager: IPermissionManager;

  /**
   * The notebook panel containing the notebook.
   */
  notebookPanel: NotebookPanel;

  /**
   * The translator for internationalization.
   */
  translator?: ITranslator;
}

/**
 * A component that displays a dialog for managing access permissions in collaborative notebooks.
 * 
 * This component allows notebook owners to control who can view, comment on, or edit the document.
 * It displays a list of current collaborators with their permission levels and provides controls
 * for adding new users, changing permission roles, and removing access.
 */
export const PermissionsDialog: React.FC<IPermissionsDialogProps> = ({
  permissionManager,
  notebookPanel,
  translator = nullTranslator
}) => {
  const trans = translator.load('notebook');

  // State for user permissions
  const [userPermissions, setUserPermissions] = useState<Map<string, IUserPermission>>(
    new Map()
  );

  // State for cell permissions
  const [cellPermissions, setCellPermissions] = useState<Map<string, ICellPermission>>(
    new Map()
  );

  // State for new user form
  const [newUserId, setNewUserId] = useState('');
  const [newUserDisplayName, setNewUserDisplayName] = useState('');
  const [newUserRole, setNewUserRole] = useState<DocumentRole>(DocumentRole.Viewer);

  // State for cell permission form
  const [selectedCellId, setSelectedCellId] = useState('');
  const [selectedCellPermission, setSelectedCellPermission] = useState<CellPermission>(CellPermission.Default);
  const [selectedCellAllowedUsers, setSelectedCellAllowedUsers] = useState<string[]>([]);

  // State for active tab
  const [activeTab, setActiveTab] = useState<'users' | 'cells'>('users');

  // State for showing error messages
  const [errorMessage, setErrorMessage] = useState('');

  // Load permissions when the component mounts
  useEffect(() => {
    const loadPermissions = () => {
      setUserPermissions(permissionManager.getAllUserPermissions());
      setCellPermissions(permissionManager.getAllCellPermissions());
    };

    // Load initial permissions
    loadPermissions();

    // Subscribe to permission changes
    const onPermissionsChanged = () => {
      loadPermissions();
    };

    permissionManager.permissionsChanged.connect(onPermissionsChanged);

    return () => {
      permissionManager.permissionsChanged.disconnect(onPermissionsChanged);
    };
  }, [permissionManager]);

  // Populate cell dropdown when the component mounts
  useEffect(() => {
    if (notebookPanel.content.model && notebookPanel.content.model.cells.length > 0) {
      // Set the first cell as the default selected cell
      setSelectedCellId(notebookPanel.content.model.cells.get(0).id);
    }
  }, [notebookPanel]);

  /**
   * Handle adding a new user.
   */
  const handleAddUser = async () => {
    // Validate inputs
    if (!newUserId.trim()) {
      setErrorMessage(trans.__('User ID is required'));
      return;
    }

    if (!newUserDisplayName.trim()) {
      setErrorMessage(trans.__('Display name is required'));
      return;
    }

    // Clear any previous error
    setErrorMessage('');

    try {
      // Add the user with the specified role
      const success = await permissionManager.setUserRole(
        newUserId.trim(),
        newUserDisplayName.trim(),
        newUserRole
      );

      if (success) {
        // Clear the form
        setNewUserId('');
        setNewUserDisplayName('');
        setNewUserRole(DocumentRole.Viewer);

        // Log the permission change
        console.log(
          `Permission granted: ${newUserRole} role assigned to ${newUserDisplayName} (${newUserId}) by ${permissionManager.currentUserDisplayName}`
        );
      } else {
        setErrorMessage(trans.__('Failed to add user. Check if you have permission or if the user already exists.'));
      }
    } catch (error) {
      setErrorMessage(trans.__('An error occurred while adding the user: ') + error.message);
      console.error('Error adding user:', error);
    }
  };

  /**
   * Handle changing a user's role.
   * 
   * @param userId - The ID of the user to update.
   * @param displayName - The display name of the user.
   * @param newRole - The new role to assign.
   */
  const handleChangeRole = async (userId: string, displayName: string, newRole: DocumentRole) => {
    try {
      const success = await permissionManager.setUserRole(userId, displayName, newRole);

      if (success) {
        // Log the permission change
        console.log(
          `Permission changed: ${newRole} role assigned to ${displayName} (${userId}) by ${permissionManager.currentUserDisplayName}`
        );
      } else {
        setErrorMessage(trans.__('Failed to change user role. Check if you have permission.'));
      }
    } catch (error) {
      setErrorMessage(trans.__('An error occurred while changing the role: ') + error.message);
      console.error('Error changing role:', error);
    }
  };

  /**
   * Handle removing a user's access.
   * 
   * @param userId - The ID of the user to remove.
   * @param displayName - The display name of the user.
   */
  const handleRemoveUser = async (userId: string, displayName: string) => {
    try {
      const success = await permissionManager.removeUserRole(userId);

      if (success) {
        // Log the permission change
        console.log(
          `Permission removed: Access revoked for ${displayName} (${userId}) by ${permissionManager.currentUserDisplayName}`
        );
      } else {
        setErrorMessage(trans.__('Failed to remove user. Check if you have permission.'));
      }
    } catch (error) {
      setErrorMessage(trans.__('An error occurred while removing the user: ') + error.message);
      console.error('Error removing user:', error);
    }
  };

  /**
   * Handle setting cell permission.
   */
  const handleSetCellPermission = async () => {
    if (!selectedCellId) {
      setErrorMessage(trans.__('Please select a cell'));
      return;
    }

    // Clear any previous error
    setErrorMessage('');

    try {
      let success: boolean;

      if (selectedCellPermission === CellPermission.Default) {
        // Reset to default permission
        success = await permissionManager.resetCellPermission(selectedCellId);
      } else {
        // Set specific permission
        success = await permissionManager.setCellPermission(
          selectedCellId,
          selectedCellPermission,
          selectedCellPermission === CellPermission.Restricted ? selectedCellAllowedUsers : undefined
        );
      }

      if (success) {
        // Log the permission change
        console.log(
          `Cell permission set: ${selectedCellPermission} for cell ${selectedCellId} by ${permissionManager.currentUserDisplayName}`
        );
      } else {
        setErrorMessage(trans.__('Failed to set cell permission. Check if you have permission.'));
      }
    } catch (error) {
      setErrorMessage(trans.__('An error occurred while setting cell permission: ') + error.message);
      console.error('Error setting cell permission:', error);
    }
  };

  /**
   * Handle cell permission type change.
   * 
   * @param permissionType - The new permission type.
   */
  const handleCellPermissionTypeChange = (permissionType: CellPermission) => {
    setSelectedCellPermission(permissionType);

    // If switching to restricted, initialize allowed users with current user
    if (permissionType === CellPermission.Restricted && selectedCellAllowedUsers.length === 0) {
      setSelectedCellAllowedUsers([permissionManager.currentUserId]);
    }
  };

  /**
   * Toggle a user in the allowed users list for restricted cells.
   * 
   * @param userId - The ID of the user to toggle.
   */
  const toggleAllowedUser = (userId: string) => {
    if (selectedCellAllowedUsers.includes(userId)) {
      // Remove user if already in the list
      setSelectedCellAllowedUsers(selectedCellAllowedUsers.filter(id => id !== userId));
    } else {
      // Add user if not in the list
      setSelectedCellAllowedUsers([...selectedCellAllowedUsers, userId]);
    }
  };

  /**
   * Get the display name for a role.
   * 
   * @param role - The role to get the display name for.
   * @returns The display name for the role.
   */
  const getRoleDisplayName = (role: DocumentRole): string => {
    switch (role) {
      case DocumentRole.Owner:
        return trans.__('Owner');
      case DocumentRole.Admin:
        return trans.__('Admin');
      case DocumentRole.Editor:
        return trans.__('Editor');
      case DocumentRole.Commenter:
        return trans.__('Commenter');
      case DocumentRole.Viewer:
        return trans.__('Viewer');
      default:
        return role;
    }
  };

  /**
   * Get the display name for a cell permission type.
   * 
   * @param permissionType - The permission type to get the display name for.
   * @returns The display name for the permission type.
   */
  const getCellPermissionDisplayName = (permissionType: CellPermission): string => {
    switch (permissionType) {
      case CellPermission.Default:
        return trans.__('Default (Follow Document Permissions)');
      case CellPermission.Protected:
        return trans.__('Protected (Only Owners & Admins)');
      case CellPermission.Restricted:
        return trans.__('Restricted (Specific Users)');
      default:
        return permissionType;
    }
  };

  /**
   * Get the description for a role.
   * 
   * @param role - The role to get the description for.
   * @returns The description for the role.
   */
  const getRoleDescription = (role: DocumentRole): string => {
    switch (role) {
      case DocumentRole.Owner:
        return trans.__('Full control, including permission management');
      case DocumentRole.Admin:
        return trans.__('Can modify content and manage permissions');
      case DocumentRole.Editor:
        return trans.__('Can modify notebook content and execute cells');
      case DocumentRole.Commenter:
        return trans.__('Can add comments but cannot modify content');
      case DocumentRole.Viewer:
        return trans.__('Read-only access to the notebook');
      default:
        return '';
    }
  };

  /**
   * Get the cell display name.
   * 
   * @param cellId - The ID of the cell.
   * @returns The display name for the cell.
   */
  const getCellDisplayName = (cellId: string): string => {
    if (!notebookPanel.content.model) {
      return cellId;
    }

    // Find the cell index
    const cells = notebookPanel.content.model.cells;
    for (let i = 0; i < cells.length; i++) {
      if (cells.get(i).id === cellId) {
        // Get the first few characters of the cell content
        const content = cells.get(i).value.text.substring(0, 20);
        return `Cell ${i + 1}: ${content}${content.length >= 20 ? '...' : ''}`;
      }
    }

    return `Cell ID: ${cellId}`;
  };

  /**
   * Render the user permissions tab.
   */
  const renderUserPermissionsTab = () => {
    return (
      <div className="jp-PermissionsDialog-userPermissions">
        {/* Current users section */}
        <div className="jp-PermissionsDialog-section">
          <h3 className="jp-PermissionsDialog-sectionTitle">
            {trans.__('Current Collaborators')}
          </h3>
          <div className="jp-PermissionsDialog-userList">
            {userPermissions.size === 0 ? (
              <div className="jp-PermissionsDialog-emptyState">
                {trans.__('No collaborators yet')}
              </div>
            ) : (
              Array.from(userPermissions.entries()).map(([userId, permission]) => (
                <div key={userId} className="jp-PermissionsDialog-userItem">
                  <div className="jp-PermissionsDialog-userInfo">
                    <div className="jp-PermissionsDialog-userName">
                      {permission.displayName}
                      {userId === permissionManager.currentUserId && 
                        <span className="jp-PermissionsDialog-currentUser">
                          {trans.__(" (you)")} 
                        </span>
                      }
                    </div>
                    <div className="jp-PermissionsDialog-userId">{userId}</div>
                    <div className="jp-PermissionsDialog-userMeta">
                      {trans.__('Added by')}: {permission.grantedBy === userId ? trans.__('self') : permission.grantedBy}
                      {' • '}
                      {trans.__('Added')}: {Time.formatHuman(new Date(permission.grantedAt))}
                    </div>
                  </div>
                  <div className="jp-PermissionsDialog-userControls">
                    <select 
                      className="jp-PermissionsDialog-roleSelect"
                      value={permission.role}
                      onChange={(e) => handleChangeRole(userId, permission.displayName, e.target.value as DocumentRole)}
                      disabled={!permissionManager.isAdmin || permission.role === DocumentRole.Owner}
                      title={getRoleDescription(permission.role)}
                    >
                      {Object.values(DocumentRole).map(role => (
                        <option key={role} value={role} disabled={role === DocumentRole.Owner && permission.role !== DocumentRole.Owner}>
                          {getRoleDisplayName(role)}
                        </option>
                      ))}
                    </select>
                    {permission.role !== DocumentRole.Owner && permissionManager.isAdmin && (
                      <button 
                        className="jp-PermissionsDialog-removeButton"
                        onClick={() => handleRemoveUser(userId, permission.displayName)}
                        title={trans.__('Remove access')}
                      >
                        <span className="jp-PermissionsDialog-removeIcon" />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Add new user section */}
        {permissionManager.isAdmin && (
          <div className="jp-PermissionsDialog-section">
            <h3 className="jp-PermissionsDialog-sectionTitle">
              {trans.__('Add New Collaborator')}
            </h3>
            <div className="jp-PermissionsDialog-addUserForm">
              <div className="jp-PermissionsDialog-formRow">
                <div className="jp-PermissionsDialog-formField">
                  <label className="jp-PermissionsDialog-label" htmlFor="userId">
                    {trans.__('User ID')}
                  </label>
                  <input
                    id="userId"
                    className="jp-PermissionsDialog-input"
                    type="text"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    placeholder={trans.__('Enter user ID')}
                  />
                </div>
                <div className="jp-PermissionsDialog-formField">
                  <label className="jp-PermissionsDialog-label" htmlFor="displayName">
                    {trans.__('Display Name')}
                  </label>
                  <input
                    id="displayName"
                    className="jp-PermissionsDialog-input"
                    type="text"
                    value={newUserDisplayName}
                    onChange={(e) => setNewUserDisplayName(e.target.value)}
                    placeholder={trans.__('Enter display name')}
                  />
                </div>
              </div>
              <div className="jp-PermissionsDialog-formRow">
                <div className="jp-PermissionsDialog-formField">
                  <label className="jp-PermissionsDialog-label" htmlFor="role">
                    {trans.__('Role')}
                  </label>
                  <select
                    id="role"
                    className="jp-PermissionsDialog-roleSelect"
                    value={newUserRole}
                    onChange={(e) => setNewUserRole(e.target.value as DocumentRole)}
                  >
                    {Object.values(DocumentRole)
                      .filter(role => role !== DocumentRole.Owner) // Don't allow creating new owners
                      .map(role => (
                        <option key={role} value={role}>
                          {getRoleDisplayName(role)} - {getRoleDescription(role)}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
              <div className="jp-PermissionsDialog-formActions">
                <button 
                  className="jp-PermissionsDialog-addButton"
                  onClick={handleAddUser}
                >
                  {trans.__('Add Collaborator')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  /**
   * Render the cell permissions tab.
   */
  const renderCellPermissionsTab = () => {
    // Get all cells from the notebook
    const cells = notebookPanel.content.model?.cells;
    const cellOptions = [];
    
    if (cells) {
      for (let i = 0; i < cells.length; i++) {
        const cell = cells.get(i);
        cellOptions.push({
          id: cell.id,
          index: i,
          preview: cell.value.text.substring(0, 20) + (cell.value.text.length > 20 ? '...' : '')
        });
      }
    }

    return (
      <div className="jp-PermissionsDialog-cellPermissions">
        {/* Current cell permissions section */}
        <div className="jp-PermissionsDialog-section">
          <h3 className="jp-PermissionsDialog-sectionTitle">
            {trans.__('Cell Permissions')}
          </h3>
          <div className="jp-PermissionsDialog-cellList">
            {cellPermissions.size === 0 ? (
              <div className="jp-PermissionsDialog-emptyState">
                {trans.__('No custom cell permissions set')}
              </div>
            ) : (
              Array.from(cellPermissions.entries()).map(([cellId, permission]) => (
                <div key={cellId} className="jp-PermissionsDialog-cellItem">
                  <div className="jp-PermissionsDialog-cellInfo">
                    <div className="jp-PermissionsDialog-cellName">
                      {getCellDisplayName(cellId)}
                    </div>
                    <div className="jp-PermissionsDialog-cellPermissionType">
                      {getCellPermissionDisplayName(permission.permissionType)}
                      {permission.permissionType === CellPermission.Restricted && permission.allowedUsers && (
                        <div className="jp-PermissionsDialog-allowedUsers">
                          {trans.__('Allowed users')}: 
                          {permission.allowedUsers.map(userId => {
                            const user = userPermissions.get(userId);
                            return user ? user.displayName : userId;
                          }).join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                  {permissionManager.isAdmin && (
                    <div className="jp-PermissionsDialog-cellControls">
                      <button 
                        className="jp-PermissionsDialog-editButton"
                        onClick={() => {
                          setSelectedCellId(cellId);
                          setSelectedCellPermission(permission.permissionType);
                          setSelectedCellAllowedUsers(permission.allowedUsers || []);
                        }}
                        title={trans.__('Edit permission')}
                      >
                        <span className="jp-PermissionsDialog-editIcon" />
                      </button>
                      <button 
                        className="jp-PermissionsDialog-removeButton"
                        onClick={() => permissionManager.resetCellPermission(cellId)}
                        title={trans.__('Reset to default')}
                      >
                        <span className="jp-PermissionsDialog-removeIcon" />
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Set cell permission section */}
        {permissionManager.isAdmin && (
          <div className="jp-PermissionsDialog-section">
            <h3 className="jp-PermissionsDialog-sectionTitle">
              {trans.__('Set Cell Permission')}
            </h3>
            <div className="jp-PermissionsDialog-setCellPermissionForm">
              <div className="jp-PermissionsDialog-formRow">
                <div className="jp-PermissionsDialog-formField">
                  <label className="jp-PermissionsDialog-label" htmlFor="cellId">
                    {trans.__('Cell')}
                  </label>
                  <select
                    id="cellId"
                    className="jp-PermissionsDialog-select"
                    value={selectedCellId}
                    onChange={(e) => setSelectedCellId(e.target.value)}
                  >
                    {cellOptions.map(cell => (
                      <option key={cell.id} value={cell.id}>
                        {`Cell ${cell.index + 1}: ${cell.preview}`}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="jp-PermissionsDialog-formField">
                  <label className="jp-PermissionsDialog-label" htmlFor="permissionType">
                    {trans.__('Permission Type')}
                  </label>
                  <select
                    id="permissionType"
                    className="jp-PermissionsDialog-select"
                    value={selectedCellPermission}
                    onChange={(e) => handleCellPermissionTypeChange(e.target.value as CellPermission)}
                  >
                    {Object.values(CellPermission).map(permType => (
                      <option key={permType} value={permType}>
                        {getCellPermissionDisplayName(permType)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Allowed users section for restricted cells */}
              {selectedCellPermission === CellPermission.Restricted && (
                <div className="jp-PermissionsDialog-allowedUsersSection">
                  <label className="jp-PermissionsDialog-label">
                    {trans.__('Allowed Users')}
                  </label>
                  <div className="jp-PermissionsDialog-allowedUsersList">
                    {Array.from(userPermissions.entries()).map(([userId, permission]) => (
                      <div key={userId} className="jp-PermissionsDialog-allowedUserItem">
                        <label className="jp-PermissionsDialog-checkboxLabel">
                          <input
                            type="checkbox"
                            checked={selectedCellAllowedUsers.includes(userId)}
                            onChange={() => toggleAllowedUser(userId)}
                          />
                          <span className="jp-PermissionsDialog-allowedUserName">
                            {permission.displayName}
                            {userId === permissionManager.currentUserId && 
                              <span className="jp-PermissionsDialog-currentUser">
                                {trans.__(" (you)")} 
                              </span>
                            }
                          </span>
                        </label>
                      </div>
                    ))}
                  </div>
                  {selectedCellAllowedUsers.length === 0 && (
                    <div className="jp-PermissionsDialog-warning">
                      {trans.__('Warning: No users selected. Cell will be locked for everyone.')}
                    </div>
                  )}
                </div>
              )}

              <div className="jp-PermissionsDialog-formActions">
                <button 
                  className="jp-PermissionsDialog-setButton"
                  onClick={handleSetCellPermission}
                >
                  {trans.__('Set Permission')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="jp-PermissionsDialog">
      {/* Tabs */}
      <div className="jp-PermissionsDialog-tabs">
        <button
          className={`jp-PermissionsDialog-tab ${activeTab === 'users' ? 'jp-PermissionsDialog-activeTab' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          {trans.__('User Permissions')}
        </button>
        <button
          className={`jp-PermissionsDialog-tab ${activeTab === 'cells' ? 'jp-PermissionsDialog-activeTab' : ''}`}
          onClick={() => setActiveTab('cells')}
        >
          {trans.__('Cell Permissions')}
        </button>
      </div>

      {/* Tab content */}
      <div className="jp-PermissionsDialog-content">
        {activeTab === 'users' ? renderUserPermissionsTab() : renderCellPermissionsTab()}
      </div>

      {/* Error message */}
      {errorMessage && (
        <div className="jp-PermissionsDialog-error">
          {errorMessage}
        </div>
      )}
    </div>
  );
};

/**
 * A namespace for PermissionsDialog statics.
 */
export namespace PermissionsDialog {
  /**
   * Open a permissions dialog.
   *
   * @param options - The dialog options.
   * @returns A promise that resolves with whether the dialog was accepted.
   */
  export function showDialog(options: Partial<IPermissionsDialogProps> & { permissionManager: IPermissionManager, notebookPanel: NotebookPanel }): Promise<Dialog.IResult<void>> {
    const dialog = new Dialog({
      title: options.translator?.load('notebook').__('Collaboration Permissions') || 'Collaboration Permissions',
      body: (
        <PermissionsDialog
          permissionManager={options.permissionManager}
          notebookPanel={options.notebookPanel}
          translator={options.translator}
        />
      ),
      buttons: [Dialog.okButton({ label: options.translator?.load('notebook').__('Close') || 'Close' })]
    });

    return dialog.launch();
  }

  /**
   * Create a new PermissionsDialog component wrapped in a ReactWidget.
   *
   * @param props - The component props.
   * @returns A new PermissionsDialog widget.
   */
  export function create(props: IPermissionsDialogProps): ReactWidget {
    const widget = ReactWidget.create(<PermissionsDialog {...props} />);
    widget.addClass('jp-PermissionsDialogWidget');
    return widget;
  }

  /**
   * Create the CSS for the PermissionsDialog component.
   * 
   * @returns The CSS for the PermissionsDialog component.
   */
  export function createStyle(): HTMLElement {
    const style = document.createElement('style');
    style.textContent = `
      .jp-PermissionsDialog {
        display: flex;
        flex-direction: column;
        min-width: 600px;
        max-width: 800px;
        max-height: 500px;
        overflow: hidden;
      }

      .jp-PermissionsDialog-tabs {
        display: flex;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-PermissionsDialog-tab {
        padding: 8px 16px;
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        cursor: pointer;
        color: var(--jp-ui-font-color1);
        font-size: var(--jp-ui-font-size1);
      }

      .jp-PermissionsDialog-tab:hover {
        background-color: var(--jp-layout-color2);
      }

      .jp-PermissionsDialog-activeTab {
        border-bottom: 2px solid var(--jp-brand-color1);
        font-weight: bold;
      }

      .jp-PermissionsDialog-content {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
      }

      .jp-PermissionsDialog-section {
        margin-bottom: 24px;
      }

      .jp-PermissionsDialog-sectionTitle {
        font-size: var(--jp-ui-font-size2);
        font-weight: bold;
        margin-top: 0;
        margin-bottom: 12px;
        color: var(--jp-ui-font-color0);
      }

      .jp-PermissionsDialog-userList,
      .jp-PermissionsDialog-cellList {
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        max-height: 200px;
        overflow-y: auto;
      }

      .jp-PermissionsDialog-userItem,
      .jp-PermissionsDialog-cellItem {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-PermissionsDialog-userItem:last-child,
      .jp-PermissionsDialog-cellItem:last-child {
        border-bottom: none;
      }

      .jp-PermissionsDialog-userInfo,
      .jp-PermissionsDialog-cellInfo {
        flex: 1;
        min-width: 0;
      }

      .jp-PermissionsDialog-userName,
      .jp-PermissionsDialog-cellName {
        font-weight: bold;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .jp-PermissionsDialog-currentUser {
        font-style: italic;
        font-weight: normal;
        color: var(--jp-ui-font-color2);
      }

      .jp-PermissionsDialog-userId,
      .jp-PermissionsDialog-cellPermissionType {
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color2);
        margin-top: 2px;
      }

      .jp-PermissionsDialog-userMeta {
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color3);
        margin-top: 2px;
      }

      .jp-PermissionsDialog-userControls,
      .jp-PermissionsDialog-cellControls {
        display: flex;
        align-items: center;
        margin-left: 12px;
      }

      .jp-PermissionsDialog-roleSelect,
      .jp-PermissionsDialog-select,
      .jp-PermissionsDialog-input {
        padding: 4px 8px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        background-color: var(--jp-layout-color1);
        color: var(--jp-ui-font-color1);
        font-size: var(--jp-ui-font-size1);
        min-width: 120px;
      }

      .jp-PermissionsDialog-input {
        width: 100%;
      }

      .jp-PermissionsDialog-removeButton,
      .jp-PermissionsDialog-editButton {
        background: none;
        border: none;
        padding: 4px;
        margin-left: 8px;
        cursor: pointer;
        border-radius: 3px;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .jp-PermissionsDialog-removeButton:hover,
      .jp-PermissionsDialog-editButton:hover {
        background-color: var(--jp-layout-color2);
      }

      .jp-PermissionsDialog-removeIcon {
        display: inline-block;
        width: 16px;
        height: 16px;
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>');
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
      }

      .jp-PermissionsDialog-editIcon {
        display: inline-block;
        width: 16px;
        height: 16px;
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>');
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
      }

      .jp-PermissionsDialog-addUserForm,
      .jp-PermissionsDialog-setCellPermissionForm {
        margin-top: 12px;
      }

      .jp-PermissionsDialog-formRow {
        display: flex;
        margin-bottom: 12px;
      }

      .jp-PermissionsDialog-formField {
        flex: 1;
        margin-right: 12px;
      }

      .jp-PermissionsDialog-formField:last-child {
        margin-right: 0;
      }

      .jp-PermissionsDialog-label {
        display: block;
        margin-bottom: 4px;
        font-size: var(--jp-ui-font-size1);
        color: var(--jp-ui-font-color1);
      }

      .jp-PermissionsDialog-formActions {
        display: flex;
        justify-content: flex-end;
        margin-top: 16px;
      }

      .jp-PermissionsDialog-addButton,
      .jp-PermissionsDialog-setButton {
        background-color: var(--jp-brand-color1);
        color: white;
        border: none;
        border-radius: 3px;
        padding: 6px 12px;
        font-size: var(--jp-ui-font-size1);
        cursor: pointer;
      }

      .jp-PermissionsDialog-addButton:hover,
      .jp-PermissionsDialog-setButton:hover {
        background-color: var(--jp-brand-color0);
      }

      .jp-PermissionsDialog-emptyState {
        padding: 16px;
        text-align: center;
        color: var(--jp-ui-font-color2);
        font-style: italic;
      }

      .jp-PermissionsDialog-error {
        margin-top: 16px;
        padding: 8px 12px;
        background-color: rgba(244, 67, 54, 0.1);
        color: #f44336;
        border-radius: 3px;
        font-size: var(--jp-ui-font-size1);
      }

      .jp-PermissionsDialog-allowedUsersSection {
        margin-top: 12px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        padding: 12px;
      }

      .jp-PermissionsDialog-allowedUsersList {
        max-height: 150px;
        overflow-y: auto;
        margin-top: 8px;
      }

      .jp-PermissionsDialog-allowedUserItem {
        margin-bottom: 4px;
      }

      .jp-PermissionsDialog-checkboxLabel {
        display: flex;
        align-items: center;
        cursor: pointer;
      }

      .jp-PermissionsDialog-checkboxLabel input {
        margin-right: 8px;
      }

      .jp-PermissionsDialog-allowedUsers {
        margin-top: 4px;
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color2);
      }

      .jp-PermissionsDialog-warning {
        margin-top: 8px;
        color: #ff9800;
        font-size: var(--jp-ui-font-size0);
      }

      /* Responsive adjustments */
      @media (max-width: 600px) {
        .jp-PermissionsDialog {
          min-width: 300px;
        }

        .jp-PermissionsDialog-formRow {
          flex-direction: column;
        }

        .jp-PermissionsDialog-formField {
          margin-right: 0;
          margin-bottom: 12px;
        }
      }
    `;
    return style;
  }
}