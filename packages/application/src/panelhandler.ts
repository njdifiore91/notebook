// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ICommandPalette } from '@jupyterlab/apputils';
import { closeIcon } from '@jupyterlab/ui-components';
import { ArrayExt, find } from '@lumino/algorithm';
import { IDisposable } from '@lumino/disposable';
import { IMessageHandler, Message, MessageLoop } from '@lumino/messaging';
import { ISignal, Signal } from '@lumino/signaling';
import { Panel, StackedPanel, Widget } from '@lumino/widgets';

/**
 * Interface for collaboration status information
 */
export interface ICollaborationStatus {
  /**
   * Whether collaboration is enabled
   */
  enabled: boolean;

  /**
   * Whether the client is connected to the collaboration server
   */
  connected: boolean;

  /**
   * The number of active users in the collaborative session
   */
  userCount: number;

  /**
   * The list of active users in the collaborative session
   */
  users: ICollaborationUser[];
}

/**
 * Interface for collaboration user information
 */
export interface ICollaborationUser {
  /**
   * The unique ID of the user
   */
  id: string;

  /**
   * The display name of the user
   */
  name: string;

  /**
   * The color assigned to the user for visual identification
   */
  color: string;

  /**
   * The avatar URL of the user
   */
  avatarUrl?: string;

  /**
   * The current location of the user in the document
   */
  location?: string;

  /**
   * The last activity timestamp of the user
   */
  lastActive?: number;

  /**
   * Whether the user is currently active
   */
  isActive: boolean;
}

/**
 * A class which manages a panel and sorts its widgets by rank.
 */
export class PanelHandler {
  constructor() {
    MessageLoop.installMessageHook(this._panel, this._panelChildHook);
  }

  /**
   * Get the panel managed by the handler.
   */
  get panel(): Panel {
    return this._panel;
  }

  /**
   * Get the collaboration status for this panel.
   */
  get collaborationStatus(): ICollaborationStatus | null {
    return this._collaborationStatus;
  }

  /**
   * Set the collaboration status for this panel.
   */
  set collaborationStatus(status: ICollaborationStatus | null) {
    this._collaborationStatus = status;
    this._collaborationStatusChanged.emit(status);
  }

  /**
   * Signal emitted when the collaboration status changes.
   */
  get collaborationStatusChanged(): ISignal<PanelHandler, ICollaborationStatus | null> {
    return this._collaborationStatusChanged;
  }

  /**
   * Whether this panel has collaboration features enabled.
   */
  get hasCollaboration(): boolean {
    return !!this._collaborationStatus?.enabled;
  }

  /**
   * Add a widget to the panel.
   *
   * If the widget is already added, it will be moved.
   */
  addWidget(widget: Widget, rank: number): void {
    widget.parent = null;
    const item = { widget, rank };
    const index = ArrayExt.upperBound(this._items, item, Private.itemCmp);
    ArrayExt.insert(this._items, index, item);
    this._panel.insertWidget(index, widget);
  }
  
  /**
   * Add a collaboration status indicator to the panel.
   * 
   * @param widget - The widget to add.
   * @param rank - The rank of the widget.
   */
  addCollaborationIndicator(widget: Widget, rank: number): void {
    this._collaborationIndicator = widget;
    this.addWidget(widget, rank);
  }
  
  /**
   * Update the collaboration status indicator.
   * 
   * @param status - The new collaboration status.
   */
  updateCollaborationStatus(status: ICollaborationStatus): void {
    this.collaborationStatus = status;
  }

  /**
   * A message hook for child remove messages on the panel handler.
   */
  private _panelChildHook = (
    handler: IMessageHandler,
    msg: Message
  ): boolean => {
    switch (msg.type) {
      case 'child-removed':
        {
          const widget = (msg as Widget.ChildMessage).child;
          ArrayExt.removeFirstWhere(this._items, (v) => v.widget === widget);
          
          // If the collaboration indicator is removed, clear the reference
          if (widget === this._collaborationIndicator) {
            this._collaborationIndicator = null;
          }
        }
        break;
      default:
        break;
    }
    return true;
  };

  protected _items = new Array<Private.IRankItem>();
  protected _panel = new Panel();
  protected _collaborationStatus: ICollaborationStatus | null = null;
  protected _collaborationIndicator: Widget | null = null;
  protected _collaborationStatusChanged = new Signal<PanelHandler, ICollaborationStatus | null>(this);
}

/**
 * A class which manages a side panel that can show at most one widget at a time.
 */
export class SidePanelHandler extends PanelHandler {
  /**
   * Construct a new side panel handler.
   */
  constructor(area: SidePanel.Area) {
    super();
    this._area = area;
    this._panel.hide();

    this._currentWidget = null;
    this._lastCurrentWidget = null;

    this._widgetPanel = new StackedPanel();
    this._widgetPanel.widgetRemoved.connect(this._onWidgetRemoved, this);

    this._closeButton = document.createElement('button');
    closeIcon.element({
      container: this._closeButton,
      height: '16px',
      width: 'auto',
    });
    this._closeButton.onclick = () => {
      this.collapse();
      this.hide();
    };
    this._closeButton.className = 'jp-Button jp-SidePanel-collapse';
    this._closeButton.title = 'Collapse side panel';

    const icon = new Widget({ node: this._closeButton });
    this._panel.addWidget(icon);
    this._panel.addWidget(this._widgetPanel);
    
    // Create container for user presence indicators
    this._userPresenceContainer = document.createElement('div');
    this._userPresenceContainer.className = 'jp-SidePanel-userPresence';
    this._userPresenceContainer.style.display = 'none';
    
    // Create user presence widget
    this._userPresenceWidget = new Widget({ node: this._userPresenceContainer });
    this._panel.addWidget(this._userPresenceWidget);
  }

  /**
   * Get the current widget in the sidebar panel.
   */
  get currentWidget(): Widget | null {
    return (
      this._currentWidget ||
      this._lastCurrentWidget ||
      (this._items.length > 0 ? this._items[0].widget : null)
    );
  }

  /**
   * Get the area of the side panel
   */
  get area(): SidePanel.Area {
    return this._area;
  }

  /**
   * Whether the panel is visible
   */
  get isVisible(): boolean {
    return this._panel.isVisible;
  }

  /**
   * Get the stacked panel managed by the handler
   */
  get panel(): Panel {
    return this._panel;
  }

  /**
   * Get the widgets list.
   */
  get widgets(): Readonly<Widget[]> {
    return this._items.map((obj) => obj.widget);
  }

  /**
   * Signal fired when a widget is added to the panel
   */
  get widgetAdded(): ISignal<SidePanelHandler, Widget> {
    return this._widgetAdded;
  }

  /**
   * Signal fired when a widget is removed from the panel
   */
  get widgetRemoved(): ISignal<SidePanelHandler, Widget> {
    return this._widgetRemoved;
  }

  /**
   * Get the close button element.
   */
  get closeButton(): HTMLButtonElement {
    return this._closeButton;
  }
  
  /**
   * Get the user presence container element.
   */
  get userPresenceContainer(): HTMLDivElement {
    return this._userPresenceContainer;
  }
  
  /**
   * Update the user presence indicators in the side panel.
   * 
   * @param users - The list of active users to display.
   */
  updateUserPresence(users: ICollaborationUser[]): void {
    // Clear existing user presence indicators
    this._userPresenceContainer.innerHTML = '';
    
    // If there are no users or collaboration is not enabled, hide the container
    if (!users.length || !this.hasCollaboration) {
      this._userPresenceContainer.style.display = 'none';
      return;
    }
    
    // Show the container
    this._userPresenceContainer.style.display = 'flex';
    
    // Add user avatars for each active user (up to a maximum of 5)
    const maxVisibleUsers = 5;
    const visibleUsers = users.slice(0, maxVisibleUsers);
    const remainingUsers = users.length > maxVisibleUsers ? users.length - maxVisibleUsers : 0;
    
    // Create avatar elements for visible users
    visibleUsers.forEach(user => {
      const avatar = document.createElement('div');
      avatar.className = 'jp-SidePanel-userAvatar';
      avatar.style.backgroundColor = user.color;
      avatar.setAttribute('data-user-id', user.id);
      avatar.setAttribute('title', user.name);
      avatar.setAttribute('aria-label', `${user.name} is ${user.isActive ? 'active' : 'inactive'}`);
      
      // If user has an avatar URL, use it
      if (user.avatarUrl) {
        avatar.style.backgroundImage = `url(${user.avatarUrl})`;
        avatar.style.backgroundSize = 'cover';
      } else {
        // Otherwise, use the first letter of their name
        avatar.textContent = user.name.charAt(0).toUpperCase();
      }
      
      // Add active/inactive status
      if (!user.isActive) {
        avatar.classList.add('jp-SidePanel-userAvatar-inactive');
      }
      
      this._userPresenceContainer.appendChild(avatar);
    });
    
    // If there are additional users, add a count indicator
    if (remainingUsers > 0) {
      const moreUsers = document.createElement('div');
      moreUsers.className = 'jp-SidePanel-userAvatar jp-SidePanel-moreUsers';
      moreUsers.textContent = `+${remainingUsers}`;
      moreUsers.setAttribute('title', `${remainingUsers} more users`);
      moreUsers.setAttribute('aria-label', `${remainingUsers} more users`);
      this._userPresenceContainer.appendChild(moreUsers);
    }
  }

  /**
   * Expand the sidebar.
   *
   * #### Notes
   * This will open the most recently used widget, or the first widget
   * if there is no most recently used.
   */
  expand(id?: string): void {
    if (id) {
      if (this._currentWidget && this._currentWidget.id === id) {
        this.collapse();
        this.hide();
      } else {
        this.collapse();
        this.hide();
        this.activate(id);
        this.show();
      }
    } else if (this.currentWidget) {
      this._currentWidget = this.currentWidget;
      this.activate(this._currentWidget.id);
      this.show();
    }
  }

  /**
   * Activate a widget residing in the stacked panel by ID.
   *
   * @param id - The widget's unique ID.
   */
  activate(id: string): void {
    const widget = this._findWidgetByID(id);
    if (widget) {
      this._currentWidget = widget;
      widget.show();
      widget.activate();
    }
  }

  /**
   * Test whether the sidebar has the given widget by id.
   */
  has(id: string): boolean {
    return this._findWidgetByID(id) !== null;
  }

  /**
   * Collapse the sidebar so no items are expanded.
   */
  collapse(): void {
    this._currentWidget?.hide();
    this._currentWidget = null;
  }

  /**
   * Add a widget and its title to the stacked panel.
   *
   * If the widget is already added, it will be moved.
   */
  addWidget(widget: Widget, rank: number): void {
    widget.parent = null;
    widget.hide();
    const item = { widget, rank };
    const index = this._findInsertIndex(item);
    ArrayExt.insert(this._items, index, item);
    this._widgetPanel.insertWidget(index, widget);

    this._refreshVisibility();

    this._widgetAdded.emit(widget);
  }

  /**
   * Hide the side panel
   */
  hide(): void {
    this._isHiddenByUser = true;
    this._refreshVisibility();
  }

  /**
   * Show the side panel
   */
  show(): void {
    this._isHiddenByUser = false;
    this._refreshVisibility();
  }

  /**
   * Find the insertion index for a rank item.
   */
  private _findInsertIndex(item: Private.IRankItem): number {
    return ArrayExt.upperBound(this._items, item, Private.itemCmp);
  }

  /**
   * Find the index of the item with the given widget, or `-1`.
   */
  private _findWidgetIndex(widget: Widget): number {
    return ArrayExt.findFirstIndex(this._items, (i) => i.widget === widget);
  }

  /**
   * Find the widget with the given id, or `null`.
   */
  private _findWidgetByID(id: string): Widget | null {
    const item = find(this._items, (value) => value.widget.id === id);
    return item ? item.widget : null;
  }

  /**
   * Refresh the visibility of the stacked panel.
   */
  private _refreshVisibility(): void {
    this._panel.setHidden(this._isHiddenByUser);
    
    // Update user presence visibility based on collaboration status
    if (this.hasCollaboration && this.collaborationStatus?.users?.length) {
      this.updateUserPresence(this.collaborationStatus.users);
    } else {
      this._userPresenceContainer.style.display = 'none';
    }
  }

  /*
   * Handle the `widgetRemoved` signal from the panel.
   */
  private _onWidgetRemoved(sender: StackedPanel, widget: Widget): void {
    if (widget === this._lastCurrentWidget) {
      this._lastCurrentWidget = null;
    }
    ArrayExt.removeAt(this._items, this._findWidgetIndex(widget));

    this._refreshVisibility();

    this._widgetRemoved.emit(widget);
  }

  /**
   * Update the collaboration status and refresh the panel.
   * 
   * @param status - The new collaboration status.
   */
  updateCollaborationStatus(status: ICollaborationStatus): void {
    super.updateCollaborationStatus(status);
    
    // Update user presence indicators if collaboration is enabled
    if (status.enabled && status.users.length > 0) {
      this.updateUserPresence(status.users);
    } else {
      this._userPresenceContainer.style.display = 'none';
    }
    
    this._refreshVisibility();
  }
  
  private _area: SidePanel.Area;
  private _isHiddenByUser = false;
  private _widgetPanel: StackedPanel;
  private _currentWidget: Widget | null;
  private _lastCurrentWidget: Widget | null;
  private _closeButton: HTMLButtonElement;
  private _userPresenceContainer: HTMLDivElement;
  private _userPresenceWidget: Widget;
  private _widgetAdded: Signal<SidePanelHandler, Widget> = new Signal(this);
  private _widgetRemoved: Signal<SidePanelHandler, Widget> = new Signal(this);
}

/**
 * A name space for SideBarPanel functions.
 */
export namespace SidePanel {
  /**
   * The areas of the sidebar panel
   */
  export type Area = 'left' | 'right';
  
  /**
   * The collaboration status of the panel
   */
  export interface ICollaborationOptions {
    /**
     * Whether to show user presence indicators
     */
    showUserPresence?: boolean;
    
    /**
     * Whether to show collaboration status indicator
     */
    showStatusIndicator?: boolean;
    
    /**
     * The maximum number of user avatars to show
     */
    maxVisibleUsers?: number;
  }
}

/**
 * A class to manages the palette entries associated to the side panels.
 */
export class SidePanelPalette {
  /**
   * Construct a new side panel palette.
   */
  constructor(options: SidePanelPaletteOption) {
    this._commandPalette = options.commandPalette;
    this._command = options.command;
    this._collaborationCommand = options.collaborationCommand || '';
  }

  /**
   * Get a command palette item from the widget id and the area.
   */
  getItem(
    widget: Readonly<Widget>,
    area: 'left' | 'right'
  ): SidePanelPaletteItem | null {
    const itemList = this._items;
    for (let i = 0; i < itemList.length; i++) {
      const item = itemList[i];
      if (item.widgetId === widget.id && item.area === area) {
        return item;
      }
    }
    return null;
  }

  /**
   * Add an item to the command palette.
   */
  addItem(widget: Readonly<Widget>, area: 'left' | 'right'): void {
    // Check if the item does not already exist.
    if (this.getItem(widget, area)) {
      return;
    }

    // Add a new item in command palette.
    const disposableDelegate = this._commandPalette.addItem({
      command: this._command,
      category: 'View',
      args: {
        side: area,
        title: `Show ${widget.title.caption}`,
        id: widget.id,
      },
    });

    // Keep the disposableDelegate object to be able to dispose of the item if the widget
    // is remove from the side panel.
    this._items.push({
      widgetId: widget.id,
      area: area,
      disposable: disposableDelegate,
    });
  }
  
  /**
   * Add a collaboration-specific item to the command palette.
   * 
   * @param widget - The widget to add.
   * @param area - The area of the panel.
   * @param collaborationType - The type of collaboration feature.
   */
  addCollaborationItem(widget: Readonly<Widget>, area: 'left' | 'right', collaborationType: string): void {
    // Skip if no collaboration command is defined
    if (!this._collaborationCommand) {
      return;
    }
    
    // Generate a unique ID for this collaboration item
    const collaborationId = `${widget.id}-${collaborationType}`;
    
    // Check if the item does not already exist
    if (this.getCollaborationItem(collaborationId, area)) {
      return;
    }
    
    // Add a new item in command palette
    const disposableDelegate = this._commandPalette.addItem({
      command: this._collaborationCommand,
      category: 'Collaboration',
      args: {
        side: area,
        title: `${collaborationType} for ${widget.title.caption}`,
        id: widget.id,
        collaborationType: collaborationType
      },
    });
    
    // Keep the disposableDelegate object
    this._collaborationItems.push({
      id: collaborationId,
      widgetId: widget.id,
      area: area,
      type: collaborationType,
      disposable: disposableDelegate
    });
  }
  
  /**
   * Get a collaboration-specific command palette item.
   * 
   * @param id - The unique ID of the collaboration item.
   * @param area - The area of the panel.
   */
  getCollaborationItem(id: string, area: 'left' | 'right'): CollaborationPaletteItem | null {
    const itemList = this._collaborationItems;
    for (let i = 0; i < itemList.length; i++) {
      const item = itemList[i];
      if (item.id === id && item.area === area) {
        return item;
      }
    }
    return null;
  }

  /**
   * Remove an item from the command palette.
   */
  removeItem(widget: Readonly<Widget>, area: 'left' | 'right'): void {
    const item = this.getItem(widget, area);
    if (item) {
      item.disposable.dispose();
    }
    
    // Also remove any collaboration items for this widget
    this.removeCollaborationItems(widget.id, area);
  }
  
  /**
   * Remove collaboration-specific items for a widget from the command palette.
   * 
   * @param widgetId - The ID of the widget.
   * @param area - The area of the panel.
   */
  removeCollaborationItems(widgetId: string, area: 'left' | 'right'): void {
    // Find all collaboration items for this widget and area
    const itemsToRemove = this._collaborationItems.filter(
      item => item.widgetId === widgetId && item.area === area
    );
    
    // Dispose of each item
    itemsToRemove.forEach(item => {
      item.disposable.dispose();
    });
    
    // Remove items from the array
    this._collaborationItems = this._collaborationItems.filter(
      item => !(item.widgetId === widgetId && item.area === area)
    );
  }

  _command: string;
  _collaborationCommand: string;
  _commandPalette: ICommandPalette;
  _items: SidePanelPaletteItem[] = [];
  _collaborationItems: CollaborationPaletteItem[] = [];
}

type SidePanelPaletteItem = {
  /**
   * The ID of the widget associated to the command palette.
   */
  widgetId: string;

  /**
   * The area of the panel associated to the command palette.
   */
  area: 'left' | 'right';

  /**
   * The disposable object to remove the item from command palette.
   */
  disposable: IDisposable;
};

/**
 * Interface for collaboration-specific command palette items.
 */
type CollaborationPaletteItem = {
  /**
   * The unique ID of this collaboration item.
   */
  id: string;
  
  /**
   * The ID of the widget associated to the command palette.
   */
  widgetId: string;

  /**
   * The area of the panel associated to the command palette.
   */
  area: 'left' | 'right';
  
  /**
   * The type of collaboration feature.
   */
  type: string;

  /**
   * The disposable object to remove the item from command palette.
   */
  disposable: IDisposable;
};

/**
 * An interface for the options to include in SideBarPalette constructor.
 */
type SidePanelPaletteOption = {
  /**
   * The commands palette.
   */
  commandPalette: ICommandPalette;

  /**
   * The command to call from each side panel menu entry.
   *
   * ### Notes
   * That command required 3 args :
   *      side: 'left' | 'right', the area to toggle
   *      title: string, label of the command
   *      id: string, id of the widget to activate
   */
  command: string;
  
  /**
   * The command to call for collaboration-specific features.
   * 
   * ### Notes
   * This command requires 4 args:
   *      side: 'left' | 'right', the area to toggle
   *      title: string, label of the command
   *      id: string, id of the widget to activate
   *      collaborationType: string, the type of collaboration feature
   */
  collaborationCommand?: string;
};

/**
 * A namespace for private module data.
 */
namespace Private {
  /**
   * An object which holds a widget and its sort rank.
   */
  export interface IRankItem {
    /**
     * The widget for the item.
     */
    widget: Widget;

    /**
     * The sort rank of the widget.
     */
    rank: number;
  }
  /**
   * A less-than comparison function for side bar rank items.
   */
  export function itemCmp(first: IRankItem, second: IRankItem): number {
    return first.rank - second.rank;
  }
}