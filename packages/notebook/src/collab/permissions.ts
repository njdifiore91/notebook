// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { INotebookModel } from '../model';
import * as Y from 'yjs';

/**
 * The document-level roles for collaborative notebook editing.
 */
export enum DocumentRole {
  /**
   * Owner role - Full control of the document, including permission assignment and deletion rights.
   */
  Owner = 'owner',

  /**
   * Admin role - Can modify content, manage permissions, and control collaborative sessions.
   */
  Admin = 'admin',

  /**
   * Editor role - Can modify notebook content and execute cells.
   */
  Editor = 'editor',

  /**
   * Commenter role - Can add comments but cannot modify notebook content.
   */
  Commenter = 'commenter',

  /**
   * Viewer role - Read-only access to the notebook.
   */
  Viewer = 'viewer'
}

/**
 * The cell-level roles for collaborative notebook editing.
 */
export enum CellRole {
  /**
   * Cell Owner - Has primary control over an individual cell.
   */
  Owner = 'cell-owner',

  /**
   * Cell Editor - Can modify the specific cell's content.
   */
  Editor = 'cell-editor',

  /**
   * Cell Executor - Can run the cell but not modify its content.
   */
  Executor = 'cell-executor',

  /**
   * Cell Commenter - Can attach comments to the cell.
   */
  Commenter = 'cell-commenter',

  /**
   * Cell Viewer - Can only view the cell content and output.
   */
  Viewer = 'cell-viewer'
}

/**
 * The cell protection levels for collaborative notebook editing.
 */
export enum CellProtectionLevel {
  /**
   * None - No additional protection beyond document-level permissions.
   */
  None = 'none',

  /**
   * Protected - Only cell owner and document admins/owners can edit.
   */
  Protected = 'protected',

  /**
   * Restricted - Only document admins/owners can edit.
   */
  Restricted = 'restricted'
}

/**
 * The permission assignment for a user.
 */
export interface IUserPermission {
  /**
   * The user ID.
   */
  userId: string;

  /**
   * The user's display name.
   */
  displayName: string;

  /**
   * The document role assigned to the user.
   */
  role: DocumentRole;
}

/**
 * The cell-level permission assignment.
 */
export interface ICellPermission {
  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The protection level for the cell.
   */
  protectionLevel: CellProtectionLevel;

  /**
   * The owner of the cell (if any).
   */
  ownerId?: string;

  /**
   * The specific user permissions for this cell (overrides document-level permissions).
   */
  userPermissions?: { [userId: string]: CellRole };
}

/**
 * The permission manager interface for collaborative notebook editing.
 */
export interface IPermissionManager {
  /**
   * A signal emitted when document permissions change.
   */
  readonly permissionsChanged: ISignal<IPermissionManager, void>;

  /**
   * A signal emitted when cell permissions change.
   */
  readonly cellPermissionsChanged: ISignal<IPermissionManager, string>;

  /**
   * The current user's ID.
   */
  readonly currentUserId: string;

  /**
   * The current user's display name.
   */
  readonly currentUserDisplayName: string;

  /**
   * The current user's role in the document.
   */
  readonly currentUserRole: DocumentRole;

  /**
   * Whether the current user is the owner of the document.
   */
  readonly isOwner: boolean;

  /**
   * Whether the current user is an admin of the document.
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
   * Get all user permissions for the document.
   */
  getUserPermissions(): IUserPermission[];

  /**
   * Get a specific user's permission.
   * 
   * @param userId - The user ID.
   */
  getUserPermission(userId: string): IUserPermission | undefined;

  /**
   * Set a user's document role.
   * 
   * @param userId - The user ID.
   * @param role - The document role to assign.
   * @param displayName - The user's display name.
   */
  setUserRole(userId: string, role: DocumentRole, displayName?: string): void;

  /**
   * Check if a user has a specific document role or higher.
   * 
   * @param userId - The user ID.
   * @param role - The document role to check.
   */
  hasDocumentRole(userId: string, role: DocumentRole): boolean;

  /**
   * Get the protection level for a cell.
   * 
   * @param cellId - The cell ID.
   */
  getCellProtectionLevel(cellId: string): CellProtectionLevel;

  /**
   * Set the protection level for a cell.
   * 
   * @param cellId - The cell ID.
   * @param level - The protection level to set.
   */
  setCellProtectionLevel(cellId: string, level: CellProtectionLevel): void;

  /**
   * Get the owner of a cell.
   * 
   * @param cellId - The cell ID.
   */
  getCellOwner(cellId: string): string | undefined;

  /**
   * Set the owner of a cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID to set as owner.
   */
  setCellOwner(cellId: string, userId: string | undefined): void;

  /**
   * Get a user's role for a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  getCellRole(cellId: string, userId: string): CellRole;

  /**
   * Set a user's role for a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   * @param role - The cell role to assign.
   */
  setCellRole(cellId: string, userId: string, role: CellRole): void;

  /**
   * Check if a user can edit a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canEditCell(cellId: string, userId: string): boolean;

  /**
   * Check if a user can execute a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canExecuteCell(cellId: string, userId: string): boolean;

  /**
   * Check if a user can comment on a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canCommentOnCell(cellId: string, userId: string): boolean;

  /**
   * Connect the permission manager to a notebook model.
   * 
   * @param model - The notebook model.
   */
  connectNotebook(model: INotebookModel): void;

  /**
   * Disconnect the permission manager from a notebook model.
   */
  disconnectNotebook(): void;
}

/**
 * A concrete implementation of IPermissionManager.
 */
export class PermissionManager implements IPermissionManager {
  /**
   * Construct a new PermissionManager.
   * 
   * @param options - The options for the permission manager.
   */
  constructor(options: PermissionManager.IOptions = {}) {
    this._currentUserId = options.currentUserId || this._getCurrentUserIdFromJupyterHub();
    this._currentUserDisplayName = options.currentUserDisplayName || this._currentUserId;
    this._currentUserRole = options.defaultRole || DocumentRole.Viewer;
  }

  /**
   * A signal emitted when document permissions change.
   */
  get permissionsChanged(): ISignal<this, void> {
    return this._permissionsChanged;
  }

  /**
   * A signal emitted when cell permissions change.
   */
  get cellPermissionsChanged(): ISignal<this, string> {
    return this._cellPermissionsChanged;
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
   * The current user's role in the document.
   */
  get currentUserRole(): DocumentRole {
    return this.getUserPermission(this._currentUserId)?.role || this._currentUserRole;
  }

  /**
   * Whether the current user is the owner of the document.
   */
  get isOwner(): boolean {
    return this.currentUserRole === DocumentRole.Owner;
  }

  /**
   * Whether the current user is an admin of the document.
   */
  get isAdmin(): boolean {
    return this.currentUserRole === DocumentRole.Owner || 
           this.currentUserRole === DocumentRole.Admin;
  }

  /**
   * Whether the current user can edit the document.
   */
  get canEdit(): boolean {
    return this.currentUserRole === DocumentRole.Owner || 
           this.currentUserRole === DocumentRole.Admin || 
           this.currentUserRole === DocumentRole.Editor;
  }

  /**
   * Whether the current user can comment on the document.
   */
  get canComment(): boolean {
    return this.currentUserRole === DocumentRole.Owner || 
           this.currentUserRole === DocumentRole.Admin || 
           this.currentUserRole === DocumentRole.Editor || 
           this.currentUserRole === DocumentRole.Commenter;
  }

  /**
   * Get all user permissions for the document.
   */
  getUserPermissions(): IUserPermission[] {
    if (!this._ydoc || !this._yuserPermissions) {
      return [];
    }

    const permissions: IUserPermission[] = [];
    this._yuserPermissions.forEach((role, userId) => {
      const displayName = this._yuserDisplayNames.get(userId) || userId;
      permissions.push({
        userId,
        displayName,
        role: role as DocumentRole
      });
    });

    return permissions;
  }

  /**
   * Get a specific user's permission.
   * 
   * @param userId - The user ID.
   */
  getUserPermission(userId: string): IUserPermission | undefined {
    if (!this._ydoc || !this._yuserPermissions) {
      return undefined;
    }

    const role = this._yuserPermissions.get(userId) as DocumentRole | undefined;
    if (!role) {
      return undefined;
    }

    const displayName = this._yuserDisplayNames.get(userId) || userId;
    return {
      userId,
      displayName,
      role
    };
  }

  /**
   * Set a user's document role.
   * 
   * @param userId - The user ID.
   * @param role - The document role to assign.
   * @param displayName - The user's display name.
   */
  setUserRole(userId: string, role: DocumentRole, displayName?: string): void {
    if (!this._ydoc || !this._yuserPermissions) {
      return;
    }

    // Check if the current user has permission to change roles
    if (!this.isAdmin && userId !== this._currentUserId) {
      console.warn('Only admins can change other users\' roles');
      return;
    }

    // Don't allow non-owners to change the owner's role
    const currentOwner = this._findUserWithRole(DocumentRole.Owner);
    if (currentOwner === userId && !this.isOwner) {
      console.warn('Only the current owner can change the owner role');
      return;
    }

    // If setting a new owner, change the current owner to admin
    if (role === DocumentRole.Owner && currentOwner && currentOwner !== userId) {
      this._yuserPermissions.set(currentOwner, DocumentRole.Admin);
    }

    // Set the user's role
    this._yuserPermissions.set(userId, role);

    // Set the user's display name if provided
    if (displayName) {
      this._yuserDisplayNames.set(userId, displayName);
    }

    // Emit the permissions changed signal
    this._permissionsChanged.emit(void 0);
  }

  /**
   * Check if a user has a specific document role or higher.
   * 
   * @param userId - The user ID.
   * @param role - The document role to check.
   */
  hasDocumentRole(userId: string, role: DocumentRole): boolean {
    const userRole = this.getUserPermission(userId)?.role || DocumentRole.Viewer;
    return this._isRoleAtLeast(userRole, role);
  }

  /**
   * Get the protection level for a cell.
   * 
   * @param cellId - The cell ID.
   */
  getCellProtectionLevel(cellId: string): CellProtectionLevel {
    if (!this._ydoc || !this._ycellProtectionLevels) {
      return CellProtectionLevel.None;
    }

    return (this._ycellProtectionLevels.get(cellId) as CellProtectionLevel) || CellProtectionLevel.None;
  }

  /**
   * Set the protection level for a cell.
   * 
   * @param cellId - The cell ID.
   * @param level - The protection level to set.
   */
  setCellProtectionLevel(cellId: string, level: CellProtectionLevel): void {
    if (!this._ydoc || !this._ycellProtectionLevels) {
      return;
    }

    // Check if the current user has permission to change protection levels
    if (!this.canEdit) {
      console.warn('Only editors, admins, and owners can set cell protection levels');
      return;
    }

    // Set the cell protection level
    this._ycellProtectionLevels.set(cellId, level);

    // Emit the cell permissions changed signal
    this._cellPermissionsChanged.emit(cellId);
  }

  /**
   * Get the owner of a cell.
   * 
   * @param cellId - The cell ID.
   */
  getCellOwner(cellId: string): string | undefined {
    if (!this._ydoc || !this._ycellOwners) {
      return undefined;
    }

    return this._ycellOwners.get(cellId) as string | undefined;
  }

  /**
   * Set the owner of a cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID to set as owner.
   */
  setCellOwner(cellId: string, userId: string | undefined): void {
    if (!this._ydoc || !this._ycellOwners) {
      return;
    }

    // Check if the current user has permission to change cell ownership
    const currentOwner = this.getCellOwner(cellId);
    if (currentOwner && currentOwner !== this._currentUserId && !this.isAdmin) {
      console.warn('Only the cell owner or document admins can change cell ownership');
      return;
    }

    // Set or delete the cell owner
    if (userId) {
      this._ycellOwners.set(cellId, userId);
    } else {
      this._ycellOwners.delete(cellId);
    }

    // Emit the cell permissions changed signal
    this._cellPermissionsChanged.emit(cellId);
  }

  /**
   * Get a user's role for a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  getCellRole(cellId: string, userId: string): CellRole {
    if (!this._ydoc || !this._ycellUserRoles) {
      return this._documentRoleToCellRole(this.getUserPermission(userId)?.role);
    }

    // Get the cell-specific role map
    const cellRoles = this._ycellUserRoles.get(cellId) as Y.Map<CellRole> | undefined;
    if (!cellRoles) {
      return this._documentRoleToCellRole(this.getUserPermission(userId)?.role);
    }

    // Get the user's cell-specific role or fall back to document role
    const cellRole = cellRoles.get(userId) as CellRole | undefined;
    if (cellRole) {
      return cellRole;
    }

    // Check if the user is the cell owner
    const cellOwner = this.getCellOwner(cellId);
    if (cellOwner === userId) {
      return CellRole.Owner;
    }

    // Fall back to document role
    return this._documentRoleToCellRole(this.getUserPermission(userId)?.role);
  }

  /**
   * Set a user's role for a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   * @param role - The cell role to assign.
   */
  setCellRole(cellId: string, userId: string, role: CellRole): void {
    if (!this._ydoc || !this._ycellUserRoles) {
      return;
    }

    // Check if the current user has permission to change cell roles
    const cellOwner = this.getCellOwner(cellId);
    if (cellOwner && cellOwner !== this._currentUserId && !this.isAdmin) {
      console.warn('Only the cell owner or document admins can change cell roles');
      return;
    }

    // Get or create the cell-specific role map
    let cellRoles = this._ycellUserRoles.get(cellId) as Y.Map<CellRole> | undefined;
    if (!cellRoles) {
      cellRoles = new Y.Map<CellRole>();
      this._ycellUserRoles.set(cellId, cellRoles);
    }

    // Set the user's cell-specific role
    cellRoles.set(userId, role);

    // Emit the cell permissions changed signal
    this._cellPermissionsChanged.emit(cellId);
  }

  /**
   * Check if a user can edit a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canEditCell(cellId: string, userId: string): boolean {
    // Document owners and admins can always edit
    const userDocRole = this.getUserPermission(userId)?.role || DocumentRole.Viewer;
    if (userDocRole === DocumentRole.Owner || userDocRole === DocumentRole.Admin) {
      return true;
    }

    // Check cell protection level
    const protectionLevel = this.getCellProtectionLevel(cellId);
    if (protectionLevel === CellProtectionLevel.Restricted) {
      // Only admins and owners can edit restricted cells
      return false;
    }

    // Check if the user is the cell owner
    const cellOwner = this.getCellOwner(cellId);
    if (protectionLevel === CellProtectionLevel.Protected) {
      // Only the cell owner and admins/owners can edit protected cells
      return cellOwner === userId;
    }

    // Check the user's cell role
    const cellRole = this.getCellRole(cellId, userId);
    return cellRole === CellRole.Owner || 
           cellRole === CellRole.Editor;
  }

  /**
   * Check if a user can execute a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canExecuteCell(cellId: string, userId: string): boolean {
    // Document owners and admins can always execute
    const userDocRole = this.getUserPermission(userId)?.role || DocumentRole.Viewer;
    if (userDocRole === DocumentRole.Owner || userDocRole === DocumentRole.Admin) {
      return true;
    }

    // Check the user's cell role
    const cellRole = this.getCellRole(cellId, userId);
    return cellRole === CellRole.Owner || 
           cellRole === CellRole.Editor || 
           cellRole === CellRole.Executor;
  }

  /**
   * Check if a user can comment on a specific cell.
   * 
   * @param cellId - The cell ID.
   * @param userId - The user ID.
   */
  canCommentOnCell(cellId: string, userId: string): boolean {
    // Document owners, admins, editors, and commenters can comment
    const userDocRole = this.getUserPermission(userId)?.role || DocumentRole.Viewer;
    if (userDocRole === DocumentRole.Owner || 
        userDocRole === DocumentRole.Admin || 
        userDocRole === DocumentRole.Editor || 
        userDocRole === DocumentRole.Commenter) {
      return true;
    }

    // Check the user's cell role
    const cellRole = this.getCellRole(cellId, userId);
    return cellRole === CellRole.Owner || 
           cellRole === CellRole.Editor || 
           cellRole === CellRole.Commenter;
  }

  /**
   * Connect the permission manager to a notebook model.
   * 
   * @param model - The notebook model.
   */
  connectNotebook(model: INotebookModel): void {
    if (this._model === model) {
      return;
    }

    // Disconnect from any existing model
    this.disconnectNotebook();

    // Connect to the new model
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

    // Initialize shared data structures
    this._initSharedData();

    // Set up initial permissions if this is a new document
    this._initializePermissions();

    // Set up observation of shared data structures
    this._observeSharedData();
  }

  /**
   * Disconnect the permission manager from a notebook model.
   */
  disconnectNotebook(): void {
    if (!this._model) {
      return;
    }

    // Clean up observation of shared data structures
    this._unobserveSharedData();

    // Clear references
    this._model = null;
    this._ydoc = null;
    this._yuserPermissions = null;
    this._yuserDisplayNames = null;
    this._ycellProtectionLevels = null;
    this._ycellOwners = null;
    this._ycellUserRoles = null;
  }

  /**
   * Initialize the shared data structures.
   */
  private _initSharedData(): void {
    if (!this._ydoc) {
      return;
    }

    // Create or get shared data structures
    this._yuserPermissions = this._ydoc.getMap('userPermissions');
    this._yuserDisplayNames = this._ydoc.getMap('userDisplayNames');
    this._ycellProtectionLevels = this._ydoc.getMap('cellProtectionLevels');
    this._ycellOwners = this._ydoc.getMap('cellOwners');
    this._ycellUserRoles = this._ydoc.getMap('cellUserRoles');
  }

  /**
   * Initialize permissions for a new document.
   */
  private _initializePermissions(): void {
    if (!this._ydoc || !this._yuserPermissions) {
      return;
    }

    // If there are no permissions yet, set the current user as owner
    if (this._yuserPermissions.size === 0) {
      this._yuserPermissions.set(this._currentUserId, DocumentRole.Owner);
      this._yuserDisplayNames.set(this._currentUserId, this._currentUserDisplayName);
    }
  }

  /**
   * Set up observation of shared data structures.
   */
  private _observeSharedData(): void {
    if (!this._ydoc || !this._yuserPermissions) {
      return;
    }

    // Observe user permissions
    this._yuserPermissions.observe(this._onUserPermissionsChanged.bind(this));

    // Observe cell protection levels
    this._ycellProtectionLevels.observe(this._onCellProtectionLevelsChanged.bind(this));

    // Observe cell owners
    this._ycellOwners.observe(this._onCellOwnersChanged.bind(this));

    // Observe cell user roles
    this._ycellUserRoles.observe(this._onCellUserRolesChanged.bind(this));
  }

  /**
   * Clean up observation of shared data structures.
   */
  private _unobserveSharedData(): void {
    if (!this._ydoc) {
      return;
    }

    // Unobserve all shared data structures
    this._yuserPermissions?.unobserve(this._onUserPermissionsChanged.bind(this));
    this._ycellProtectionLevels?.unobserve(this._onCellProtectionLevelsChanged.bind(this));
    this._ycellOwners?.unobserve(this._onCellOwnersChanged.bind(this));
    this._ycellUserRoles?.unobserve(this._onCellUserRolesChanged.bind(this));
  }

  /**
   * Handle changes to user permissions.
   */
  private _onUserPermissionsChanged(event: Y.YMapEvent<any>): void {
    // Emit the permissions changed signal
    this._permissionsChanged.emit(void 0);
  }

  /**
   * Handle changes to cell protection levels.
   */
  private _onCellProtectionLevelsChanged(event: Y.YMapEvent<any>): void {
    // Emit the cell permissions changed signal for each changed cell
    event.keysChanged.forEach(cellId => {
      this._cellPermissionsChanged.emit(cellId);
    });
  }

  /**
   * Handle changes to cell owners.
   */
  private _onCellOwnersChanged(event: Y.YMapEvent<any>): void {
    // Emit the cell permissions changed signal for each changed cell
    event.keysChanged.forEach(cellId => {
      this._cellPermissionsChanged.emit(cellId);
    });
  }

  /**
   * Handle changes to cell user roles.
   */
  private _onCellUserRolesChanged(event: Y.YMapEvent<any>): void {
    // Emit the cell permissions changed signal for each changed cell
    event.keysChanged.forEach(cellId => {
      this._cellPermissionsChanged.emit(cellId);
    });
  }

  /**
   * Find a user with a specific role.
   * 
   * @param role - The role to find.
   */
  private _findUserWithRole(role: DocumentRole): string | undefined {
    if (!this._ydoc || !this._yuserPermissions) {
      return undefined;
    }

    let foundUser: string | undefined;
    this._yuserPermissions.forEach((userRole, userId) => {
      if (userRole === role) {
        foundUser = userId;
      }
    });

    return foundUser;
  }

  /**
   * Check if a role is at least as permissive as another role.
   * 
   * @param role - The role to check.
   * @param minRole - The minimum role required.
   */
  private _isRoleAtLeast(role: DocumentRole, minRole: DocumentRole): boolean {
    const roleHierarchy = {
      [DocumentRole.Owner]: 4,
      [DocumentRole.Admin]: 3,
      [DocumentRole.Editor]: 2,
      [DocumentRole.Commenter]: 1,
      [DocumentRole.Viewer]: 0
    };

    return roleHierarchy[role] >= roleHierarchy[minRole];
  }

  /**
   * Convert a document role to an equivalent cell role.
   * 
   * @param role - The document role to convert.
   */
  private _documentRoleToCellRole(role?: DocumentRole): CellRole {
    switch (role) {
      case DocumentRole.Owner:
      case DocumentRole.Admin:
        return CellRole.Owner;
      case DocumentRole.Editor:
        return CellRole.Editor;
      case DocumentRole.Commenter:
        return CellRole.Commenter;
      case DocumentRole.Viewer:
      default:
        return CellRole.Viewer;
    }
  }

  /**
   * Get the current user ID from JupyterHub if available.
   */
  private _getCurrentUserIdFromJupyterHub(): string {
    // Try to get the user ID from the page config
    try {
      // @ts-ignore
      const pageConfig = window.jupyter?.pageConfig;
      if (pageConfig && pageConfig.user) {
        return pageConfig.user;
      }
    } catch (error) {
      console.warn('Error getting user ID from JupyterHub:', error);
    }

    // Fall back to a generated ID if JupyterHub is not available
    return `user-${Math.random().toString(36).substring(2, 10)}`;
  }

  private _model: INotebookModel | null = null;
  private _ydoc: Y.Doc | null = null;
  private _yuserPermissions: Y.Map<DocumentRole> | null = null;
  private _yuserDisplayNames: Y.Map<string> | null = null;
  private _ycellProtectionLevels: Y.Map<CellProtectionLevel> | null = null;
  private _ycellOwners: Y.Map<string> | null = null;
  private _ycellUserRoles: Y.Map<Y.Map<CellRole>> | null = null;

  private _currentUserId: string;
  private _currentUserDisplayName: string;
  private _currentUserRole: DocumentRole;

  private _permissionsChanged = new Signal<this, void>(this);
  private _cellPermissionsChanged = new Signal<this, string>(this);
}

/**
 * The namespace for PermissionManager class statics.
 */
export namespace PermissionManager {
  /**
   * The options for initializing a permission manager.
   */
  export interface IOptions {
    /**
     * The current user ID.
     */
    currentUserId?: string;

    /**
     * The current user's display name.
     */
    currentUserDisplayName?: string;

    /**
     * The default role for the current user.
     */
    defaultRole?: DocumentRole;
  }
}