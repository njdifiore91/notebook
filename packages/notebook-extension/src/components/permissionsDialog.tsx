// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Divider,
  Tabs,
  Tab,
  Box,
  Tooltip,
  Paper,
  Switch,
  FormControlLabel,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  Delete as DeleteIcon,
  PersonAdd as PersonAddIcon,
  Info as InfoIcon,
  Lock as LockIcon,
  LockOpen as LockOpenIcon
} from '@mui/icons-material';
import { IPermissionManager, DocumentRole, CellProtectionLevel } from '@jupyterlab/notebook';

/**
 * Interface for the PermissionsDialog props.
 */
export interface IPermissionsDialogProps {
  /**
   * Whether the dialog is open.
   */
  open: boolean;

  /**
   * Callback fired when the dialog is closed.
   */
  onClose: () => void;

  /**
   * The permission manager instance.
   */
  permissionManager: IPermissionManager;

  /**
   * The notebook title for display purposes.
   */
  notebookTitle: string;

  /**
   * The list of cell IDs in the notebook.
   */
  cellIds?: string[];

  /**
   * Optional callback for logging permission changes.
   */
  onPermissionChange?: (change: {
    userId: string;
    oldRole?: DocumentRole;
    newRole?: DocumentRole;
    cellId?: string;
    protectionLevel?: CellProtectionLevel;
  }) => void;
}

/**
 * Interface for a tab panel props.
 */
interface ITabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

/**
 * A TabPanel component for the tabs in the dialog.
 */
function TabPanel(props: ITabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`permissions-tabpanel-${index}`}
      aria-labelledby={`permissions-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

/**
 * A function to get props for a tab.
 */
function a11yProps(index: number) {
  return {
    id: `permissions-tab-${index}`,
    'aria-controls': `permissions-tabpanel-${index}`
  };
}

/**
 * A dialog for managing notebook permissions.
 */
export function PermissionsDialog(props: IPermissionsDialogProps): JSX.Element {
  const { open, onClose, permissionManager, notebookTitle, cellIds, onPermissionChange } = props;

  // State for the active tab
  const [tabValue, setTabValue] = useState(0);

  // State for user permissions
  const [userPermissions, setUserPermissions] = useState<Array<{
    userId: string;
    displayName: string;
    role: DocumentRole;
  }>>([]);

  // State for new user form
  const [newUserId, setNewUserId] = useState('');
  const [newUserDisplayName, setNewUserDisplayName] = useState('');
  const [newUserRole, setNewUserRole] = useState<DocumentRole>(DocumentRole.Viewer);
  const [addUserError, setAddUserError] = useState('');

  // State for cell permissions
  const [selectedCellId, setSelectedCellId] = useState<string | undefined>(undefined);
  const [cellProtectionLevels, setCellProtectionLevels] = useState<Record<string, CellProtectionLevel>>({});
  const [cellOwners, setCellOwners] = useState<Record<string, string | undefined>>({});

  // State for loading and errors
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Load user permissions when the dialog opens or permissions change
  useEffect(() => {
    if (open) {
      loadUserPermissions();
      if (cellIds && cellIds.length > 0) {
        loadCellPermissions();
        setSelectedCellId(cellIds[0]);
      }
    }
  }, [open, permissionManager]);

  // Subscribe to permission changes
  useEffect(() => {
    if (!permissionManager) {
      return;
    }

    const onPermissionsChanged = () => {
      loadUserPermissions();
    };

    const onCellPermissionsChanged = (cellId: string) => {
      loadCellPermission(cellId);
    };

    permissionManager.permissionsChanged.connect(onPermissionsChanged);
    permissionManager.cellPermissionsChanged.connect(onCellPermissionsChanged);

    return () => {
      permissionManager.permissionsChanged.disconnect(onPermissionsChanged);
      permissionManager.cellPermissionsChanged.disconnect(onCellPermissionsChanged);
    };
  }, [permissionManager]);

  /**
   * Load all user permissions.
   */
  const loadUserPermissions = () => {
    if (!permissionManager) {
      return;
    }

    try {
      setIsLoading(true);
      const permissions = permissionManager.getUserPermissions();
      setUserPermissions(permissions);
      setError('');
    } catch (err) {
      console.error('Error loading user permissions:', err);
      setError('Failed to load user permissions');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Load all cell permissions.
   */
  const loadCellPermissions = () => {
    if (!permissionManager || !cellIds) {
      return;
    }

    try {
      setIsLoading(true);
      const protectionLevels: Record<string, CellProtectionLevel> = {};
      const owners: Record<string, string | undefined> = {};

      cellIds.forEach(cellId => {
        protectionLevels[cellId] = permissionManager.getCellProtectionLevel(cellId);
        owners[cellId] = permissionManager.getCellOwner(cellId);
      });

      setCellProtectionLevels(protectionLevels);
      setCellOwners(owners);
      setError('');
    } catch (err) {
      console.error('Error loading cell permissions:', err);
      setError('Failed to load cell permissions');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Load permissions for a specific cell.
   */
  const loadCellPermission = (cellId: string) => {
    if (!permissionManager) {
      return;
    }

    try {
      const protectionLevel = permissionManager.getCellProtectionLevel(cellId);
      const owner = permissionManager.getCellOwner(cellId);

      setCellProtectionLevels(prev => ({
        ...prev,
        [cellId]: protectionLevel
      }));

      setCellOwners(prev => ({
        ...prev,
        [cellId]: owner
      }));
    } catch (err) {
      console.error(`Error loading permissions for cell ${cellId}:`, err);
    }
  };

  /**
   * Handle tab change.
   */
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  /**
   * Handle adding a new user.
   */
  const handleAddUser = () => {
    if (!permissionManager) {
      return;
    }

    if (!newUserId.trim()) {
      setAddUserError('User ID is required');
      return;
    }

    try {
      setIsLoading(true);
      const displayName = newUserDisplayName.trim() || newUserId;
      
      // Check if user already exists
      const existingUser = userPermissions.find(user => user.userId === newUserId);
      if (existingUser) {
        setAddUserError('User already exists');
        return;
      }

      // Set the user role
      permissionManager.setUserRole(newUserId, newUserRole, displayName);

      // Log the permission change
      if (onPermissionChange) {
        onPermissionChange({
          userId: newUserId,
          newRole: newUserRole
        });
      }

      // Reset form
      setNewUserId('');
      setNewUserDisplayName('');
      setNewUserRole(DocumentRole.Viewer);
      setAddUserError('');
      
      // Reload permissions
      loadUserPermissions();
    } catch (err) {
      console.error('Error adding user:', err);
      setAddUserError('Failed to add user');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle changing a user's role.
   */
  const handleChangeUserRole = (userId: string, newRole: DocumentRole) => {
    if (!permissionManager) {
      return;
    }

    try {
      setIsLoading(true);
      const oldRole = permissionManager.getUserPermission(userId)?.role;
      
      // Set the user role
      permissionManager.setUserRole(userId, newRole);

      // Log the permission change
      if (onPermissionChange) {
        onPermissionChange({
          userId,
          oldRole,
          newRole
        });
      }

      // Reload permissions
      loadUserPermissions();
    } catch (err) {
      console.error(`Error changing role for user ${userId}:`, err);
      setError(`Failed to change role for user ${userId}`);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle removing a user.
   */
  const handleRemoveUser = (userId: string) => {
    if (!permissionManager) {
      return;
    }

    // Don't allow removing the current user
    if (userId === permissionManager.currentUserId) {
      setError('You cannot remove yourself');
      return;
    }

    try {
      setIsLoading(true);
      const oldRole = permissionManager.getUserPermission(userId)?.role;
      
      // Remove the user by setting their role to undefined
      // This is equivalent to removing them from the permissions list
      permissionManager.setUserRole(userId, undefined as any);

      // Log the permission change
      if (onPermissionChange) {
        onPermissionChange({
          userId,
          oldRole,
          newRole: undefined
        });
      }

      // Reload permissions
      loadUserPermissions();
    } catch (err) {
      console.error(`Error removing user ${userId}:`, err);
      setError(`Failed to remove user ${userId}`);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle changing a cell's protection level.
   */
  const handleChangeCellProtectionLevel = (cellId: string, level: CellProtectionLevel) => {
    if (!permissionManager) {
      return;
    }

    try {
      setIsLoading(true);
      
      // Set the cell protection level
      permissionManager.setCellProtectionLevel(cellId, level);

      // Log the permission change
      if (onPermissionChange) {
        onPermissionChange({
          cellId,
          protectionLevel: level
        });
      }

      // Update local state
      setCellProtectionLevels(prev => ({
        ...prev,
        [cellId]: level
      }));
    } catch (err) {
      console.error(`Error changing protection level for cell ${cellId}:`, err);
      setError(`Failed to change protection level for cell ${cellId}`);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle changing a cell's owner.
   */
  const handleChangeCellOwner = (cellId: string, userId: string | undefined) => {
    if (!permissionManager) {
      return;
    }

    try {
      setIsLoading(true);
      
      // Set the cell owner
      permissionManager.setCellOwner(cellId, userId);

      // Log the permission change
      if (onPermissionChange) {
        onPermissionChange({
          cellId,
          userId: userId || ''
        });
      }

      // Update local state
      setCellOwners(prev => ({
        ...prev,
        [cellId]: userId
      }));
    } catch (err) {
      console.error(`Error changing owner for cell ${cellId}:`, err);
      setError(`Failed to change owner for cell ${cellId}`);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Get the display name for a role.
   */
  const getRoleDisplayName = (role: DocumentRole): string => {
    switch (role) {
      case DocumentRole.Owner:
        return 'Owner';
      case DocumentRole.Admin:
        return 'Admin';
      case DocumentRole.Editor:
        return 'Editor';
      case DocumentRole.Commenter:
        return 'Commenter';
      case DocumentRole.Viewer:
        return 'Viewer';
      default:
        return 'Unknown';
    }
  };

  /**
   * Get the display name for a protection level.
   */
  const getProtectionLevelDisplayName = (level: CellProtectionLevel): string => {
    switch (level) {
      case CellProtectionLevel.None:
        return 'None';
      case CellProtectionLevel.Protected:
        return 'Protected';
      case CellProtectionLevel.Restricted:
        return 'Restricted';
      default:
        return 'Unknown';
    }
  };

  /**
   * Get the description for a protection level.
   */
  const getProtectionLevelDescription = (level: CellProtectionLevel): string => {
    switch (level) {
      case CellProtectionLevel.None:
        return 'No additional protection beyond document-level permissions.';
      case CellProtectionLevel.Protected:
        return 'Only cell owner and document admins/owners can edit.';
      case CellProtectionLevel.Restricted:
        return 'Only document admins/owners can edit.';
      default:
        return '';
    }
  };

  /**
   * Get the description for a role.
   */
  const getRoleDescription = (role: DocumentRole): string => {
    switch (role) {
      case DocumentRole.Owner:
        return 'Full control, including permission management';
      case DocumentRole.Admin:
        return 'Can modify content, manage permissions, and control collaborative sessions';
      case DocumentRole.Editor:
        return 'Can modify notebook content and execute cells';
      case DocumentRole.Commenter:
        return 'Can add comments but cannot modify notebook content';
      case DocumentRole.Viewer:
        return 'Read-only access to the notebook';
      default:
        return '';
    }
  };

  /**
   * Render the document permissions tab.
   */
  const renderDocumentPermissionsTab = () => {
    return (
      <>
        <Typography variant="h6" gutterBottom>
          Document Permissions
        </Typography>
        <Typography variant="body2" color="textSecondary" paragraph>
          Manage who can access and edit this notebook. Document-level permissions apply to the entire notebook unless overridden by cell-specific permissions.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Paper variant="outlined" sx={{ mb: 3 }}>
          <List>
            {userPermissions.map((user) => (
              <ListItem key={user.userId}>
                <ListItemText
                  primary={
                    <>
                      {user.displayName}
                      {user.userId === permissionManager.currentUserId && (
                        <Typography component="span" color="primary" sx={{ ml: 1 }}>
                          (You)
                        </Typography>
                      )}
                    </>
                  }
                  secondary={user.userId}
                />
                <FormControl variant="outlined" size="small" sx={{ minWidth: 120, mr: 1 }}>
                  <Select
                    value={user.role}
                    onChange={(e) => handleChangeUserRole(user.userId, e.target.value as DocumentRole)}
                    disabled={
                      user.role === DocumentRole.Owner ||
                      !permissionManager.isAdmin ||
                      user.userId === permissionManager.currentUserId
                    }
                  >
                    <MenuItem value={DocumentRole.Owner}>
                      <Typography variant="body2">Owner</Typography>
                    </MenuItem>
                    <MenuItem value={DocumentRole.Admin}>
                      <Typography variant="body2">Admin</Typography>
                    </MenuItem>
                    <MenuItem value={DocumentRole.Editor}>
                      <Typography variant="body2">Editor</Typography>
                    </MenuItem>
                    <MenuItem value={DocumentRole.Commenter}>
                      <Typography variant="body2">Commenter</Typography>
                    </MenuItem>
                    <MenuItem value={DocumentRole.Viewer}>
                      <Typography variant="body2">Viewer</Typography>
                    </MenuItem>
                  </Select>
                </FormControl>
                <Tooltip title={getRoleDescription(user.role)}>
                  <IconButton size="small">
                    <InfoIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <ListItemSecondaryAction>
                  <Tooltip title="Remove user">
                    <span>
                      <IconButton
                        edge="end"
                        aria-label="delete"
                        onClick={() => handleRemoveUser(user.userId)}
                        disabled={
                          user.role === DocumentRole.Owner ||
                          !permissionManager.isAdmin ||
                          user.userId === permissionManager.currentUserId
                        }
                      >
                        <DeleteIcon />
                      </IconButton>
                    </span>
                  </Tooltip>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
          </List>
        </Paper>

        {permissionManager.isAdmin && (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              Add New User
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'flex-end', flexWrap: 'wrap', gap: 2 }}>
              <TextField
                label="User ID"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                variant="outlined"
                size="small"
                error={!!addUserError}
                helperText={addUserError}
                sx={{ flexGrow: 1, minWidth: '200px' }}
              />
              <TextField
                label="Display Name (optional)"
                value={newUserDisplayName}
                onChange={(e) => setNewUserDisplayName(e.target.value)}
                variant="outlined"
                size="small"
                sx={{ flexGrow: 1, minWidth: '200px' }}
              />
              <FormControl variant="outlined" size="small" sx={{ minWidth: '150px' }}>
                <InputLabel id="new-user-role-label">Role</InputLabel>
                <Select
                  labelId="new-user-role-label"
                  value={newUserRole}
                  onChange={(e) => setNewUserRole(e.target.value as DocumentRole)}
                  label="Role"
                >
                  <MenuItem value={DocumentRole.Admin}>
                    <Typography variant="body2">Admin</Typography>
                  </MenuItem>
                  <MenuItem value={DocumentRole.Editor}>
                    <Typography variant="body2">Editor</Typography>
                  </MenuItem>
                  <MenuItem value={DocumentRole.Commenter}>
                    <Typography variant="body2">Commenter</Typography>
                  </MenuItem>
                  <MenuItem value={DocumentRole.Viewer}>
                    <Typography variant="body2">Viewer</Typography>
                  </MenuItem>
                </Select>
              </FormControl>
              <Tooltip title={getRoleDescription(newUserRole)}>
                <IconButton size="small">
                  <InfoIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Button
                variant="contained"
                color="primary"
                startIcon={<PersonAddIcon />}
                onClick={handleAddUser}
                disabled={isLoading}
              >
                Add User
              </Button>
            </Box>
          </Paper>
        )}
      </>
    );
  };

  /**
   * Render the cell permissions tab.
   */
  const renderCellPermissionsTab = () => {
    if (!cellIds || cellIds.length === 0) {
      return (
        <Typography variant="body1" color="textSecondary">
          No cells available to configure permissions.
        </Typography>
      );
    }

    return (
      <>
        <Typography variant="h6" gutterBottom>
          Cell-Level Permissions
        </Typography>
        <Typography variant="body2" color="textSecondary" paragraph>
          Set protection levels for individual cells. Cell-level permissions override document-level permissions.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <FormControl fullWidth variant="outlined" margin="normal">
          <InputLabel id="cell-select-label">Select Cell</InputLabel>
          <Select
            labelId="cell-select-label"
            value={selectedCellId || ''}
            onChange={(e) => setSelectedCellId(e.target.value as string)}
            label="Select Cell"
          >
            {cellIds.map((cellId, index) => (
              <MenuItem key={cellId} value={cellId}>
                Cell {index + 1} ({cellId.substring(0, 8)}...)
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {selectedCellId && (
          <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              Protection Level
            </Typography>
            <FormControl fullWidth variant="outlined" margin="normal">
              <InputLabel id="protection-level-label">Protection Level</InputLabel>
              <Select
                labelId="protection-level-label"
                value={cellProtectionLevels[selectedCellId] || CellProtectionLevel.None}
                onChange={(e) => handleChangeCellProtectionLevel(selectedCellId, e.target.value as CellProtectionLevel)}
                label="Protection Level"
              >
                <MenuItem value={CellProtectionLevel.None}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <LockOpenIcon fontSize="small" sx={{ mr: 1 }} />
                    <Typography variant="body2">None</Typography>
                  </Box>
                </MenuItem>
                <MenuItem value={CellProtectionLevel.Protected}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <LockIcon fontSize="small" sx={{ mr: 1 }} />
                    <Typography variant="body2">Protected</Typography>
                  </Box>
                </MenuItem>
                <MenuItem value={CellProtectionLevel.Restricted}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <LockIcon fontSize="small" sx={{ mr: 1, color: 'error.main' }} />
                    <Typography variant="body2">Restricted</Typography>
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>
            <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
              {getProtectionLevelDescription(cellProtectionLevels[selectedCellId] || CellProtectionLevel.None)}
            </Typography>

            <Divider sx={{ my: 2 }} />

            <Typography variant="subtitle1" gutterBottom>
              Cell Owner
            </Typography>
            <FormControl fullWidth variant="outlined" margin="normal">
              <InputLabel id="cell-owner-label">Cell Owner</InputLabel>
              <Select
                labelId="cell-owner-label"
                value={cellOwners[selectedCellId] || ''}
                onChange={(e) => handleChangeCellOwner(selectedCellId, e.target.value || undefined)}
                label="Cell Owner"
              >
                <MenuItem value="">
                  <em>None</em>
                </MenuItem>
                {userPermissions.map((user) => (
                  <MenuItem key={user.userId} value={user.userId}>
                    {user.displayName} ({user.userId})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
              The cell owner has special privileges for this cell, such as being able to edit protected cells.
            </Typography>
          </Paper>
        )}
      </>
    );
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby="permissions-dialog-title"
      maxWidth="md"
      fullWidth
    >
      <DialogTitle id="permissions-dialog-title">
        <Typography variant="h6" component="div">
          Permissions for {notebookTitle}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
            <CircularProgress />
          </Box>
        )}

        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="permissions tabs">
            <Tab label="Document Permissions" {...a11yProps(0)} />
            <Tab label="Cell Permissions" {...a11yProps(1)} />
          </Tabs>
        </Box>
        <TabPanel value={tabValue} index={0}>
          {renderDocumentPermissionsTab()}
        </TabPanel>
        <TabPanel value={tabValue} index={1}>
          {renderCellPermissionsTab()}
        </TabPanel>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}