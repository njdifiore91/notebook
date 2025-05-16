// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { INotebookModel } from '../model';
import { ICollaborationProvider } from './provider';
import { Token } from '@lumino/coreutils';
import * as Y from 'yjs';
import { PageConfig } from '@jupyterlab/coreutils';

/**
 * The permission manager token.
 */
export const IPermissionManager = new Token<IPermissionManager>(
  '@jupyterlab/notebook:IPermissionManager'
);

/**
 * Document-level roles for collaborative editing.
 */
export enum DocumentRole {
  /**
   * Owner has full control of the document, including permission assignment and deletion rights.
   */
  Owner = 'owner',

  /**
   * Admin can modify content, manage permissions, and control collaborative sessions.
   */
  Admin = 'admin',

  /**
   * Editor can modify notebook content and execute cells.
   */
  Editor = 'editor',

  /**
   * Commenter can add comments but cannot modify notebook content.
   */
  Commenter = 'commenter',

  /**
   * Viewer has read-only access to the notebook.
   */
  Viewer = 'viewer'
}

/**
 * Cell-level permission types.
 */
export enum CellPermission {
  /**
   * Default permission follows document-level role.
   */
  Default = 'default',

  /**
   * Restricted cells can only be edited by specific users.
   */
  Restricted = 'restricted',

  /**
   * Protected cells can only be edited by owners and admins.
   */
  Protected = 'protected'
}

/**
 * Interface for user permission information.
 */
export interface IUserPermission {
  /**
   * The user's unique identifier.
   */
  userId: string;

  /**
   * The user's display name.
   */
  displayName: string;

  /**
   * The user's role for this document.
   */
  role: DocumentRole;

  /**
   * The time when the permission was granted.
   */
  grantedAt: number;

  /**
   * The ID of the user who granted this permission.
   */
  grantedBy: string;
}

/**
 * Interface for cell permission information.
 */
export interface ICellPermission {
  /**
   * The ID of the cell.
   */
  cellId: string;

  /**
   * The permission type for this cell.
   */
  permissionType: CellPermission;

  /**
   * List of user IDs who can edit this cell (for restricted cells).
   */
  allowedUsers?: string[];
}

/**
 * Interface for permission change events.
 */
export interface IPermissionChange {
  /**
   * The type of permission change.
   */
  type: 'document' | 'cell';

  /**
   * The user ID affected by the change (for document permissions).
   */
  userId?: string;

  /**
   * The cell ID affected by the change (for cell permissions).
   */
  cellId?: string;

  /**
   * The previous permission state.
   */
  previousValue?: DocumentRole | CellPermission | string[];

  /**
   * The new permission state.
   */
  newValue?: DocumentRole | CellPermission | string[];
}

/**
 * Interface for the permission manager.
 */
export interface IPermissionManager {
  /**
   * A signal emitted when permissions change.
   */
  readonly permissionsChanged: ISignal<IPermissionManager, IPermissionChange>;

  /**
   * The current user's ID.
   */
  readonly currentUserId: string;

  /**
   * The current user's display name.
   */
  readonly currentUserDisplayName: string;

  /**
   * Whether the current user is the owner of the document.
   */
  readonly isOwner: boolean;

  /**
   * Whether the current user is an admin for the document.
   */
  readonly isAdmin: boolean;

  /**
   * Whether the current user can edit the document.
   */
  readonly canEdit: boolean;

  /**
   * Whether the current user can comment on the document.
   */
  readonly canComment: boolean;

  /**
   * Connect the permission manager to a notebook model.
   *
   * @param model - The notebook model to connect to.
   */
  connectNotebook(model: INotebookModel): void;

  /**
   * Disconnect the permission manager from the notebook model.
   */
  disconnectNotebook(): void;

  /**
   * Get the role of a user.
   *
   * @param userId - The ID of the user to check.
   * @returns The user's role, or undefined if the user has no explicit role.
   */
  getUserRole(userId: string): DocumentRole | undefined;

  /**
   * Set the role of a user.
   *
   * @param userId - The ID of the user to update.
   * @param displayName - The display name of the user.
   * @param role - The role to assign to the user.
   * @returns A promise that resolves to true if the role was set, false otherwise.
   */
  setUserRole(userId: string, displayName: string, role: DocumentRole): Promise<boolean>;

  /**
   * Remove a user's explicit role.
   *
   * @param userId - The ID of the user to remove.
   * @returns A promise that resolves to true if the role was removed, false otherwise.
   */
  removeUserRole(userId: string): Promise<boolean>;

  /**
   * Get all user permissions.
   *
   * @returns A map of user IDs to permission objects.
   */
  getAllUserPermissions(): Map<string, IUserPermission>;

  /**
   * Get the permission type for a cell.
   *
   * @param cellId - The ID of the cell to check.
   * @returns The cell's permission type, or CellPermission.Default if not set.
   */
  getCellPermission(cellId: string): CellPermission;

  /**
   * Set the permission type for a cell.
   *
   * @param cellId - The ID of the cell to update.
   * @param permissionType - The permission type to set.
   * @param allowedUsers - Optional list of user IDs who can edit this cell (for restricted cells).
   * @returns A promise that resolves to true if the permission was set, false otherwise.
   */
  setCellPermission(
    cellId: string,
    permissionType: CellPermission,
    allowedUsers?: string[]
  ): Promise<boolean>;

  /**
   * Reset a cell's permission to default.
   *
   * @param cellId - The ID of the cell to reset.
   * @returns A promise that resolves to true if the permission was reset, false otherwise.
   */
  resetCellPermission(cellId: string): Promise<boolean>;

  /**
   * Get all cell permissions.
   *
   * @returns A map of cell IDs to permission objects.
   */
  getAllCellPermissions(): Map<string, ICellPermission>;

  /**
   * Check if a user can edit a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can edit the cell, false otherwise.
   */
  canEditCell(cellId: string, userId?: string): boolean;

  /**
   * Check if a user can comment on a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can comment on the cell, false otherwise.
   */
  canCommentOnCell(cellId: string, userId?: string): boolean;

  /**
   * Check if a user can execute a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can execute the cell, false otherwise.
   */
  canExecuteCell(cellId: string, userId?: string): boolean;
}

/**
 * Implementation of the permission manager.
 */
export class PermissionManager implements IPermissionManager {
  /**
   * Construct a new PermissionManager.
   *
   * @param options - The options for the permission manager.
   */
  constructor(options: PermissionManager.IOptions = {}) {
    this._currentUserId = options.userId || this._getCurrentUserId();
    this._currentUserDisplayName = options.displayName || this._getCurrentUserDisplayName();
  }

  /**
   * A signal emitted when permissions change.
   */
  get permissionsChanged(): ISignal<IPermissionManager, IPermissionChange> {
    return this._permissionsChanged;
  }

  /**
   * The current user's ID.
   */
  get currentUserId(): string {
    return this._currentUserId;
  }

  /**
   * The current user's display name.
   */
  get currentUserDisplayName(): string {
    return this._currentUserDisplayName;
  }

  /**
   * Whether the current user is the owner of the document.
   */
  get isOwner(): boolean {
    return this.getUserRole(this._currentUserId) === DocumentRole.Owner;
  }

  /**
   * Whether the current user is an admin for the document.
   */
  get isAdmin(): boolean {
    const role = this.getUserRole(this._currentUserId);
    return role === DocumentRole.Owner || role === DocumentRole.Admin;
  }

  /**
   * Whether the current user can edit the document.
   */
  get canEdit(): boolean {
    const role = this.getUserRole(this._currentUserId);
    return (
      role === DocumentRole.Owner ||
      role === DocumentRole.Admin ||
      role === DocumentRole.Editor
    );
  }

  /**
   * Whether the current user can comment on the document.
   */
  get canComment(): boolean {
    const role = this.getUserRole(this._currentUserId);
    return (
      role === DocumentRole.Owner ||
      role === DocumentRole.Admin ||
      role === DocumentRole.Editor ||
      role === DocumentRole.Commenter
    );
  }

  /**
   * Connect the permission manager to a notebook model.
   *
   * @param model - The notebook model to connect to.
   */
  connectNotebook(model: INotebookModel): void {
    if (this._model === model) {
      return;
    }

    // Disconnect from any existing notebook
    this.disconnectNotebook();

    // Connect to the new notebook
    this._model = model;

    // Get the Yjs document from the collaboration provider
    const provider = model.collaborationProvider;
    if (!provider) {
      console.warn('Notebook model does not have a collaboration provider');
      return;
    }

    this._ydoc = provider.ydoc;
    if (!this._ydoc) {
      console.warn('Collaboration provider does not have a Yjs document');
      return;
    }

    // Initialize the shared permissions maps
    this._yuserPermissions = this._ydoc.getMap('userPermissions');
    this._ycellPermissions = this._ydoc.getMap('cellPermissions');

    // Set up observation of the permissions maps
    this._yuserPermissions.observe(this._onUserPermissionsChanged.bind(this));
    this._ycellPermissions.observe(this._onCellPermissionsChanged.bind(this));

    // Initialize permissions if this is a new document
    this._initializePermissions();
  }

  /**
   * Disconnect the permission manager from the notebook model.
   */
  disconnectNotebook(): void {
    if (!this._model) {
      return;
    }

    // Clean up observation of the permissions maps
    if (this._yuserPermissions) {
      this._yuserPermissions.unobserve(this._onUserPermissionsChanged.bind(this));
    }

    if (this._ycellPermissions) {
      this._ycellPermissions.unobserve(this._onCellPermissionsChanged.bind(this));
    }

    // Clear references
    this._model = null;
    this._ydoc = null;
    this._yuserPermissions = null;
    this._ycellPermissions = null;
  }

  /**
   * Get the role of a user.
   *
   * @param userId - The ID of the user to check.
   * @returns The user's role, or undefined if the user has no explicit role.
   */
  getUserRole(userId: string): DocumentRole | undefined {
    if (!this._yuserPermissions) {
      return undefined;
    }

    const permission = this._yuserPermissions.get(userId) as IUserPermission | undefined;
    return permission?.role;
  }

  /**
   * Set the role of a user.
   *
   * @param userId - The ID of the user to update.
   * @param displayName - The display name of the user.
   * @param role - The role to assign to the user.
   * @returns A promise that resolves to true if the role was set, false otherwise.
   */
  async setUserRole(userId: string, displayName: string, role: DocumentRole): Promise<boolean> {
    if (!this._ydoc || !this._yuserPermissions) {
      console.warn('Permission manager not connected to a notebook');
      return false;
    }

    // Check if the current user has permission to change roles
    if (!this.isAdmin) {
      console.warn('Only owners and admins can change user roles');
      return false;
    }

    // Don't allow changing the owner's role
    const existingPermission = this._yuserPermissions.get(userId) as IUserPermission | undefined;
    if (existingPermission?.role === DocumentRole.Owner && role !== DocumentRole.Owner) {
      console.warn('Cannot change the owner\'s role');
      return false;
    }

    // Don't allow creating multiple owners
    if (role === DocumentRole.Owner) {
      // Check if there's already an owner
      let hasOwner = false;
      this._yuserPermissions.forEach((permission: any) => {
        if (permission.role === DocumentRole.Owner && permission.userId !== userId) {
          hasOwner = true;
        }
      });

      if (hasOwner) {
        console.warn('Cannot have multiple owners');
        return false;
      }
    }

    // Create or update the permission
    const newPermission: IUserPermission = {
      userId,
      displayName,
      role,
      grantedAt: Date.now(),
      grantedBy: this._currentUserId
    };

    // Update the shared data structure
    this._ydoc.transact(() => {
      this._yuserPermissions?.set(userId, newPermission);
    }, this);

    return true;
  }

  /**
   * Remove a user's explicit role.
   *
   * @param userId - The ID of the user to remove.
   * @returns A promise that resolves to true if the role was removed, false otherwise.
   */
  async removeUserRole(userId: string): Promise<boolean> {
    if (!this._ydoc || !this._yuserPermissions) {
      console.warn('Permission manager not connected to a notebook');
      return false;
    }

    // Check if the current user has permission to change roles
    if (!this.isAdmin) {
      console.warn('Only owners and admins can remove user roles');
      return false;
    }

    // Don't allow removing the owner's role
    const existingPermission = this._yuserPermissions.get(userId) as IUserPermission | undefined;
    if (existingPermission?.role === DocumentRole.Owner) {
      console.warn('Cannot remove the owner\'s role');
      return false;
    }

    // Remove the permission
    this._ydoc.transact(() => {
      this._yuserPermissions?.delete(userId);
    }, this);

    return true;
  }

  /**
   * Get all user permissions.
   *
   * @returns A map of user IDs to permission objects.
   */
  getAllUserPermissions(): Map<string, IUserPermission> {
    const permissions = new Map<string, IUserPermission>();
    if (!this._yuserPermissions) {
      return permissions;
    }

    this._yuserPermissions.forEach((permission: any, userId: string) => {
      permissions.set(userId, permission as IUserPermission);
    });

    return permissions;
  }

  /**
   * Get the permission type for a cell.
   *
   * @param cellId - The ID of the cell to check.
   * @returns The cell's permission type, or CellPermission.Default if not set.
   */
  getCellPermission(cellId: string): CellPermission {
    if (!this._ycellPermissions) {
      return CellPermission.Default;
    }

    const permission = this._ycellPermissions.get(cellId) as ICellPermission | undefined;
    return permission?.permissionType || CellPermission.Default;
  }

  /**
   * Set the permission type for a cell.
   *
   * @param cellId - The ID of the cell to update.
   * @param permissionType - The permission type to set.
   * @param allowedUsers - Optional list of user IDs who can edit this cell (for restricted cells).
   * @returns A promise that resolves to true if the permission was set, false otherwise.
   */
  async setCellPermission(
    cellId: string,
    permissionType: CellPermission,
    allowedUsers?: string[]
  ): Promise<boolean> {
    if (!this._ydoc || !this._ycellPermissions) {
      console.warn('Permission manager not connected to a notebook');
      return false;
    }

    // Check if the current user has permission to change cell permissions
    if (!this.isAdmin) {
      console.warn('Only owners and admins can change cell permissions');
      return false;
    }

    // Create the cell permission object
    const cellPermission: ICellPermission = {
      cellId,
      permissionType
    };

    // Add allowed users for restricted cells
    if (permissionType === CellPermission.Restricted && allowedUsers) {
      cellPermission.allowedUsers = allowedUsers;
    }

    // Update the shared data structure
    this._ydoc.transact(() => {
      this._ycellPermissions?.set(cellId, cellPermission);
    }, this);

    return true;
  }

  /**
   * Reset a cell's permission to default.
   *
   * @param cellId - The ID of the cell to reset.
   * @returns A promise that resolves to true if the permission was reset, false otherwise.
   */
  async resetCellPermission(cellId: string): Promise<boolean> {
    if (!this._ydoc || !this._ycellPermissions) {
      console.warn('Permission manager not connected to a notebook');
      return false;
    }

    // Check if the current user has permission to change cell permissions
    if (!this.isAdmin) {
      console.warn('Only owners and admins can reset cell permissions');
      return false;
    }

    // Remove the cell permission
    this._ydoc.transact(() => {
      this._ycellPermissions?.delete(cellId);
    }, this);

    return true;
  }

  /**
   * Get all cell permissions.
   *
   * @returns A map of cell IDs to permission objects.
   */
  getAllCellPermissions(): Map<string, ICellPermission> {
    const permissions = new Map<string, ICellPermission>();
    if (!this._ycellPermissions) {
      return permissions;
    }

    this._ycellPermissions.forEach((permission: any, cellId: string) => {
      permissions.set(cellId, permission as ICellPermission);
    });

    return permissions;
  }

  /**
   * Check if a user can edit a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can edit the cell, false otherwise.
   */
  canEditCell(cellId: string, userId?: string): boolean {
    const userIdToCheck = userId || this._currentUserId;
    const userRole = this.getUserRole(userIdToCheck);

    // If the user has no role, they can't edit
    if (!userRole) {
      return false;
    }

    // Owners and admins can edit any cell
    if (userRole === DocumentRole.Owner || userRole === DocumentRole.Admin) {
      return true;
    }

    // Editors can edit cells based on cell permissions
    if (userRole === DocumentRole.Editor) {
      const cellPermission = this.getCellPermission(cellId);

      switch (cellPermission) {
        case CellPermission.Default:
          return true;
        case CellPermission.Protected:
          return false; // Only owners and admins can edit protected cells
        case CellPermission.Restricted:
          // Check if the user is in the allowed users list
          const permission = this._ycellPermissions?.get(cellId) as ICellPermission | undefined;
          return permission?.allowedUsers?.includes(userIdToCheck) || false;
      }
    }

    // Commenters and viewers can't edit cells
    return false;
  }

  /**
   * Check if a user can comment on a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can comment on the cell, false otherwise.
   */
  canCommentOnCell(cellId: string, userId?: string): boolean {
    const userIdToCheck = userId || this._currentUserId;
    const userRole = this.getUserRole(userIdToCheck);

    // If the user has no role, they can't comment
    if (!userRole) {
      return false;
    }

    // All roles except Viewer can comment
    return (
      userRole === DocumentRole.Owner ||
      userRole === DocumentRole.Admin ||
      userRole === DocumentRole.Editor ||
      userRole === DocumentRole.Commenter
    );
  }

  /**
   * Check if a user can execute a specific cell.
   *
   * @param cellId - The ID of the cell to check.
   * @param userId - The ID of the user to check, defaults to current user.
   * @returns True if the user can execute the cell, false otherwise.
   */
  canExecuteCell(cellId: string, userId?: string): boolean {
    const userIdToCheck = userId || this._currentUserId;
    const userRole = this.getUserRole(userIdToCheck);

    // If the user has no role, they can't execute
    if (!userRole) {
      return false;
    }

    // Owners, admins, and editors can execute cells
    return (
      userRole === DocumentRole.Owner ||
      userRole === DocumentRole.Admin ||
      userRole === DocumentRole.Editor
    );
  }

  /**
   * Initialize permissions for a new document.
   */
  private _initializePermissions(): void {
    if (!this._ydoc || !this._yuserPermissions) {
      return;
    }

    // If there are no permissions yet, set the current user as the owner
    if (this._yuserPermissions.size === 0) {
      const ownerPermission: IUserPermission = {
        userId: this._currentUserId,
        displayName: this._currentUserDisplayName,
        role: DocumentRole.Owner,
        grantedAt: Date.now(),
        grantedBy: this._currentUserId
      };

      this._ydoc.transact(() => {
        this._yuserPermissions?.set(this._currentUserId, ownerPermission);
      }, this);
    }
  }

  /**
   * Handle changes to the user permissions map.
   *
   * @param event - The Y.js map event.
   */
  private _onUserPermissionsChanged(event: Y.YMapEvent<any>): void {
    // Process each changed key
    event.keysChanged.forEach(userId => {
      const previousValue = event.changes.keys.get(userId)?.oldValue as IUserPermission | undefined;
      const newValue = this._yuserPermissions?.get(userId) as IUserPermission | undefined;

      // Emit the permissions changed signal
      this._permissionsChanged.emit({
        type: 'document',
        userId,
        previousValue: previousValue?.role,
        newValue: newValue?.role
      });
    });
  }

  /**
   * Handle changes to the cell permissions map.
   *
   * @param event - The Y.js map event.
   */
  private _onCellPermissionsChanged(event: Y.YMapEvent<any>): void {
    // Process each changed key
    event.keysChanged.forEach(cellId => {
      const previousValue = event.changes.keys.get(cellId)?.oldValue as ICellPermission | undefined;
      const newValue = this._ycellPermissions?.get(cellId) as ICellPermission | undefined;

      // Emit the permissions changed signal
      this._permissionsChanged.emit({
        type: 'cell',
        cellId,
        previousValue: previousValue?.permissionType,
        newValue: newValue?.permissionType
      });

      // If this is a restricted cell, also emit a change for the allowed users
      if (
        (previousValue?.permissionType === CellPermission.Restricted ||
          newValue?.permissionType === CellPermission.Restricted) &&
        JSON.stringify(previousValue?.allowedUsers) !== JSON.stringify(newValue?.allowedUsers)
      ) {
        this._permissionsChanged.emit({
          type: 'cell',
          cellId,
          previousValue: previousValue?.allowedUsers,
          newValue: newValue?.allowedUsers
        });
      }
    });
  }

  /**
   * Get the current user's ID from JupyterHub or other sources.
   *
   * @returns The current user's ID.
   */
  private _getCurrentUserId(): string {
    // Try to get the user ID from JupyterHub
    const hubUser = PageConfig.getOption('hubUser');
    if (hubUser) {
      return hubUser;
    }

    // Try to get the user ID from the page config
    const userName = PageConfig.getOption('userName');
    if (userName) {
      return userName;
    }

    // Fallback to a generated ID
    return `user-${Math.random().toString(36).substring(2, 10)}`;
  }

  /**
   * Get the current user's display name from JupyterHub or other sources.
   *
   * @returns The current user's display name.
   */
  private _getCurrentUserDisplayName(): string {
    // Try to get the user display name from JupyterHub
    const hubUser = PageConfig.getOption('hubUser');
    if (hubUser) {
      return hubUser; // Use the hub username as display name
    }

    // Try to get the user display name from the page config
    const userName = PageConfig.getOption('userName');
    if (userName) {
      return userName;
    }

    // Fallback to 'Anonymous User'
    return 'Anonymous User';
  }

  private _model: INotebookModel | null = null;
  private _ydoc: Y.Doc | null = null;
  private _yuserPermissions: Y.Map<IUserPermission> | null = null;
  private _ycellPermissions: Y.Map<ICellPermission> | null = null;

  private _currentUserId: string;
  private _currentUserDisplayName: string;

  private _permissionsChanged = new Signal<IPermissionManager, IPermissionChange>(this);
}

/**
 * Namespace for PermissionManager.
 */
export namespace PermissionManager {
  /**
   * Options for the PermissionManager.
   */
  export interface IOptions {
    /**
     * The current user's ID.
     * If not provided, will attempt to get from JupyterHub or generate a random ID.
     */
    userId?: string;

    /**
     * The current user's display name.
     * If not provided, will attempt to get from JupyterHub or use a default.
     */
    displayName?: string;
  }
}