# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import pytest
import time
from unittest.mock import MagicMock, patch

# Import the awareness module
from notebook.collab.awareness import (
    UserStatus,
    ICursorPosition,
    ISelectionRange,
    IUserAwarenessState,
    IAwarenessChanges,
    IPresenceTracker,
    PresenceTracker
)


@pytest.fixture
def mock_awareness():
    """Create a mock Awareness instance."""
    mock = MagicMock()
    
    # Store states in a dictionary for easy testing
    mock.states = {}
    
    # Mock the setLocalState method
    def mock_set_local_state(state):
        mock.local_state = state
    mock.setLocalState = mock_set_local_state
    
    # Mock the getLocalState method
    def mock_get_local_state():
        return mock.local_state
    mock.getLocalState = mock_get_local_state
    
    # Mock the getStates method
    def mock_get_states():
        return mock.states
    mock.getStates = mock_get_states
    
    # Mock the on method to register event handlers
    mock.event_handlers = {}
    def mock_on(event, handler):
        if event not in mock.event_handlers:
            mock.event_handlers[event] = []
        mock.event_handlers[event].append(handler)
    mock.on = mock_on
    
    # Method to simulate an event
    def mock_emit_event(event, changes, origin=None):
        if event in mock.event_handlers:
            for handler in mock.event_handlers[event]:
                handler(changes, origin)
    mock.emit_event = mock_emit_event
    
    # Mock the destroy method
    def mock_destroy():
        mock.destroyed = True
    mock.destroy = mock_destroy
    
    return mock


@pytest.fixture
def mock_presence_tracker(mock_yjs_doc, mock_awareness):
    """Create a mock PresenceTracker instance."""
    with patch('y_protocols.awareness.Awareness', return_value=mock_awareness):
        tracker = PresenceTracker(mock_yjs_doc)
        yield tracker
        tracker.destroy()


@pytest.fixture
def user_state():
    """Create a sample user awareness state."""
    return {
        'userId': 'user1',
        'displayName': 'User One',
        'avatarUrl': 'https://example.com/avatar.png',
        'status': UserStatus.Active,
        'color': '#ff0000',
        'lastActivity': time.time() * 1000  # Current time in milliseconds
    }


@pytest.fixture
def cursor_position():
    """Create a sample cursor position."""
    return {
        'cellId': 'cell1',
        'offset': 10
    }


@pytest.fixture
def selection_range():
    """Create a sample selection range."""
    return {
        'startCellId': 'cell1',
        'startOffset': 5,
        'endCellId': 'cell1',
        'endOffset': 15
    }


class TestPresenceTracker:
    """Tests for the PresenceTracker class."""
    
    def test_initialization(self, mock_yjs_doc):
        """Test that the PresenceTracker initializes correctly."""
        with patch('y_protocols.awareness.Awareness') as MockAwareness:
            mock_awareness = MagicMock()
            MockAwareness.return_value = mock_awareness
            
            tracker = PresenceTracker(mock_yjs_doc)
            
            # Check that Awareness was initialized with the Yjs document
            MockAwareness.assert_called_once_with(mock_yjs_doc)
            
            # Check that the client ID was set correctly
            assert tracker.clientId == mock_yjs_doc.clientID
            
            # Check that the awareness change event handler was registered
            mock_awareness.on.assert_called_with('change', tracker._onAwarenessChange)
            
            # Clean up
            tracker.destroy()
    
    def test_set_get_local_state(self, mock_presence_tracker, user_state):
        """Test setting and getting the local user's awareness state."""
        # Set the local state
        mock_presence_tracker.setLocalState(user_state)
        
        # Get the local state
        local_state = mock_presence_tracker.getLocalState()
        
        # Check that the state was set correctly
        assert local_state is not None
        assert local_state['userId'] == user_state['userId']
        assert local_state['displayName'] == user_state['displayName']
        assert local_state['status'] == user_state['status']
        assert local_state['color'] == user_state['color']
        assert 'lastActivity' in local_state  # Should be updated automatically
    
    def test_update_local_state(self, mock_presence_tracker, user_state):
        """Test updating a specific field in the local user's awareness state."""
        # Set the initial state
        mock_presence_tracker.setLocalState(user_state)
        
        # Update a specific field
        new_status = UserStatus.Idle
        mock_presence_tracker.updateLocalState('status', new_status)
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the field was updated
        assert updated_state['status'] == new_status
        assert updated_state['userId'] == user_state['userId']  # Other fields should remain unchanged
        assert 'lastActivity' in updated_state  # Should be updated automatically
    
    def test_set_cursor_position(self, mock_presence_tracker, user_state, cursor_position):
        """Test setting the user's cursor position."""
        # Set the initial state
        mock_presence_tracker.setLocalState(user_state)
        
        # Set the cursor position
        mock_presence_tracker.setCursorPosition(cursor_position)
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the cursor position was set
        assert 'cursor' in updated_state
        assert updated_state['cursor']['cellId'] == cursor_position['cellId']
        assert updated_state['cursor']['offset'] == cursor_position['offset']
    
    def test_set_selection_range(self, mock_presence_tracker, user_state, selection_range):
        """Test setting the user's selection range."""
        # Set the initial state
        mock_presence_tracker.setLocalState(user_state)
        
        # Set the selection range
        mock_presence_tracker.setSelectionRange(selection_range)
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the selection range was set
        assert 'selection' in updated_state
        assert updated_state['selection']['startCellId'] == selection_range['startCellId']
        assert updated_state['selection']['startOffset'] == selection_range['startOffset']
        assert updated_state['selection']['endCellId'] == selection_range['endCellId']
        assert updated_state['selection']['endOffset'] == selection_range['endOffset']
    
    def test_set_status(self, mock_presence_tracker, user_state):
        """Test setting the user's status."""
        # Set the initial state
        mock_presence_tracker.setLocalState(user_state)
        
        # Set the status
        new_status = UserStatus.Editing
        mock_presence_tracker.setStatus(new_status)
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the status was set
        assert updated_state['status'] == new_status
    
    def test_mark_active(self, mock_presence_tracker, user_state):
        """Test marking the user as active."""
        # Set the initial state with Idle status
        initial_state = {**user_state, 'status': UserStatus.Idle}
        mock_presence_tracker.setLocalState(initial_state)
        
        # Get the initial lastActivity timestamp
        initial_state = mock_presence_tracker.getLocalState()
        initial_timestamp = initial_state['lastActivity']
        
        # Wait a short time to ensure the timestamp changes
        time.sleep(0.01)
        
        # Mark the user as active
        mock_presence_tracker.markActive()
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the status was changed to Active
        assert updated_state['status'] == UserStatus.Active
        
        # Check that the lastActivity timestamp was updated
        assert updated_state['lastActivity'] > initial_timestamp
    
    def test_mark_active_while_editing(self, mock_presence_tracker, user_state):
        """Test marking the user as active while they are editing."""
        # Set the initial state with Editing status
        initial_state = {**user_state, 'status': UserStatus.Editing}
        mock_presence_tracker.setLocalState(initial_state)
        
        # Get the initial lastActivity timestamp
        initial_state = mock_presence_tracker.getLocalState()
        initial_timestamp = initial_state['lastActivity']
        
        # Wait a short time to ensure the timestamp changes
        time.sleep(0.01)
        
        # Mark the user as active
        mock_presence_tracker.markActive()
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the status remains as Editing
        assert updated_state['status'] == UserStatus.Editing
        
        # Check that the lastActivity timestamp was updated
        assert updated_state['lastActivity'] > initial_timestamp
    
    def test_is_editing_cell(self, mock_presence_tracker, mock_awareness, user_state, cursor_position):
        """Test checking if a user is editing a specific cell."""
        # Set up a state where a user is editing a cell
        editing_state = {
            **user_state,
            'status': UserStatus.Editing,
            'cursor': cursor_position
        }
        
        # Add the state to the awareness states
        client_id = 1
        mock_awareness.states[client_id] = editing_state
        
        # Check if the user is editing the cell
        editing_client = mock_presence_tracker.isEditingCell(cursor_position['cellId'])
        
        # Check that the correct client ID is returned
        assert editing_client == client_id
        
        # Check for a cell that no one is editing
        not_editing_client = mock_presence_tracker.isEditingCell('non_existent_cell')
        
        # Check that null is returned
        assert not_editing_client is None
    
    def test_state_changed_signal(self, mock_presence_tracker, mock_awareness):
        """Test that the stateChanged signal is emitted when awareness changes."""
        # Create a mock handler for the stateChanged signal
        mock_handler = MagicMock()
        mock_presence_tracker.stateChanged.connect(mock_handler)
        
        # Create a changes object
        changes = {
            'added': [1],
            'updated': [2],
            'removed': [3]
        }
        
        # Simulate an awareness change event
        mock_awareness.emit_event('change', changes)
        
        # Check that the handler was called with the changes
        mock_handler.assert_called_once_with(changes)
    
    def test_check_idle_users(self, mock_presence_tracker, user_state):
        """Test that users are marked as idle after the idle timeout."""
        # Set a short idle timeout for testing
        mock_presence_tracker._idleTimeout = 100  # 100 ms
        
        # Set the initial state with Active status and an old lastActivity timestamp
        old_timestamp = time.time() * 1000 - 200  # 200 ms ago
        initial_state = {**user_state, 'status': UserStatus.Active, 'lastActivity': old_timestamp}
        mock_presence_tracker.setLocalState(initial_state)
        
        # Trigger the idle check by simulating an awareness change
        mock_presence_tracker._checkIdleUsers()
        
        # Get the updated state
        updated_state = mock_presence_tracker.getLocalState()
        
        # Check that the status was changed to Idle
        assert updated_state['status'] == UserStatus.Idle
    
    def test_cleanup_disconnected_users(self, mock_presence_tracker):
        """Test cleanup of disconnected users."""
        # This is mostly handled by the Awareness implementation,
        # but we can test that our method doesn't raise exceptions
        mock_presence_tracker._cleanupDisconnectedUsers()
        
        # No assertions needed, just checking that it runs without errors
    
    def test_destroy(self, mock_presence_tracker, mock_awareness):
        """Test destroying the presence tracker."""
        # Destroy the tracker
        mock_presence_tracker.destroy()
        
        # Check that the awareness was destroyed
        assert mock_awareness.destroyed is True
        
        # Check that the cleanup timer was cleared
        assert mock_presence_tracker._cleanupTimer is None


@pytest.mark.asyncio
class TestPresenceTrackerIntegration:
    """Integration tests for the PresenceTracker class."""
    
    async def test_multiple_users_awareness(self, mock_yjs_doc, mock_users):
        """Test awareness with multiple users."""
        # Create a real PresenceTracker instance
        tracker = PresenceTracker(mock_yjs_doc)
        
        # Set up user states for multiple users
        user_states = {}
        for user_id, user_info in mock_users.items():
            user_states[user_id] = {
                'userId': user_id,
                'displayName': user_info['name'],
                'status': UserStatus.Active,
                'color': user_info['color'],
                'lastActivity': time.time() * 1000
            }
        
        # Simulate setting states in the awareness
        for i, (user_id, state) in enumerate(user_states.items()):
            client_id = i + 1  # Start from 1
            mock_yjs_doc.clientID = client_id  # Simulate different client IDs
            tracker._awareness.states[client_id] = state
        
        # Get all states
        states = tracker.getStates()
        
        # Check that all user states are present
        assert len(states) == len(user_states)
        for i, (user_id, state) in enumerate(user_states.items()):
            client_id = i + 1
            assert client_id in states
            assert states[client_id]['userId'] == user_id
            assert states[client_id]['displayName'] == state['displayName']
        
        # Clean up
        tracker.destroy()
    
    async def test_cursor_synchronization(self, mock_yjs_doc, mock_users, cursor_position):
        """Test cursor position synchronization between users."""
        # Create a real PresenceTracker instance
        tracker = PresenceTracker(mock_yjs_doc)
        
        # Set up a handler to track awareness changes
        changes_received = []
        def on_state_changed(changes):
            changes_received.append(changes)
        tracker.stateChanged.connect(on_state_changed)
        
        # Set the local user state
        user_id = list(mock_users.keys())[0]
        user_info = mock_users[user_id]
        tracker.setLocalState({
            'userId': user_id,
            'displayName': user_info['name'],
            'status': UserStatus.Active,
            'color': user_info['color'],
            'lastActivity': time.time() * 1000
        })
        
        # Set the cursor position
        tracker.setCursorPosition(cursor_position)
        
        # Check that the cursor position was set in the local state
        local_state = tracker.getLocalState()
        assert local_state['cursor']['cellId'] == cursor_position['cellId']
        assert local_state['cursor']['offset'] == cursor_position['offset']
        
        # Simulate an awareness change event to trigger the signal
        client_id = mock_yjs_doc.clientID
        tracker._awareness.emit_event('change', {'updated': [client_id]})
        
        # Check that the change was signaled
        assert len(changes_received) > 0
        assert client_id in changes_received[-1]['updated']
        
        # Clean up
        tracker.destroy()
    
    async def test_selection_synchronization(self, mock_yjs_doc, mock_users, selection_range):
        """Test selection range synchronization between users."""
        # Create a real PresenceTracker instance
        tracker = PresenceTracker(mock_yjs_doc)
        
        # Set up a handler to track awareness changes
        changes_received = []
        def on_state_changed(changes):
            changes_received.append(changes)
        tracker.stateChanged.connect(on_state_changed)
        
        # Set the local user state
        user_id = list(mock_users.keys())[0]
        user_info = mock_users[user_id]
        tracker.setLocalState({
            'userId': user_id,
            'displayName': user_info['name'],
            'status': UserStatus.Active,
            'color': user_info['color'],
            'lastActivity': time.time() * 1000
        })
        
        # Set the selection range
        tracker.setSelectionRange(selection_range)
        
        # Check that the selection range was set in the local state
        local_state = tracker.getLocalState()
        assert local_state['selection']['startCellId'] == selection_range['startCellId']
        assert local_state['selection']['startOffset'] == selection_range['startOffset']
        assert local_state['selection']['endCellId'] == selection_range['endCellId']
        assert local_state['selection']['endOffset'] == selection_range['endOffset']
        
        # Simulate an awareness change event to trigger the signal
        client_id = mock_yjs_doc.clientID
        tracker._awareness.emit_event('change', {'updated': [client_id]})
        
        # Check that the change was signaled
        assert len(changes_received) > 0
        assert client_id in changes_received[-1]['updated']
        
        # Clean up
        tracker.destroy()
    
    async def test_status_propagation(self, mock_yjs_doc, mock_users):
        """Test user status propagation between clients."""
        # Create a real PresenceTracker instance
        tracker = PresenceTracker(mock_yjs_doc)
        
        # Set up a handler to track awareness changes
        changes_received = []
        def on_state_changed(changes):
            changes_received.append(changes)
        tracker.stateChanged.connect(on_state_changed)
        
        # Set the local user state
        user_id = list(mock_users.keys())[0]
        user_info = mock_users[user_id]
        tracker.setLocalState({
            'userId': user_id,
            'displayName': user_info['name'],
            'status': UserStatus.Active,
            'color': user_info['color'],
            'lastActivity': time.time() * 1000
        })
        
        # Change the status
        tracker.setStatus(UserStatus.Editing)
        
        # Check that the status was updated in the local state
        local_state = tracker.getLocalState()
        assert local_state['status'] == UserStatus.Editing
        
        # Simulate an awareness change event to trigger the signal
        client_id = mock_yjs_doc.clientID
        tracker._awareness.emit_event('change', {'updated': [client_id]})
        
        # Check that the change was signaled
        assert len(changes_received) > 0
        assert client_id in changes_received[-1]['updated']
        
        # Clean up
        tracker.destroy()
    
    async def test_cleanup_on_disconnect(self, mock_yjs_doc, mock_users):
        """Test cleanup of awareness state when a user disconnects."""
        # Create a real PresenceTracker instance
        tracker = PresenceTracker(mock_yjs_doc)
        
        # Set up a handler to track awareness changes
        changes_received = []
        def on_state_changed(changes):
            changes_received.append(changes)
        tracker.stateChanged.connect(on_state_changed)
        
        # Set up user states for multiple users
        client_ids = []
        for i, (user_id, user_info) in enumerate(mock_users.items()):
            client_id = i + 1  # Start from 1
            client_ids.append(client_id)
            tracker._awareness.states[client_id] = {
                'userId': user_id,
                'displayName': user_info['name'],
                'status': UserStatus.Active,
                'color': user_info['color'],
                'lastActivity': time.time() * 1000
            }
        
        # Check that all users are present
        states = tracker.getStates()
        assert len(states) == len(mock_users)
        
        # Simulate a user disconnecting by removing their state
        disconnected_client_id = client_ids[0]
        del tracker._awareness.states[disconnected_client_id]
        
        # Simulate an awareness change event to trigger the signal
        tracker._awareness.emit_event('change', {'removed': [disconnected_client_id]})
        
        # Check that the change was signaled
        assert len(changes_received) > 0
        assert disconnected_client_id in changes_received[-1]['removed']
        
        # Check that the user was removed from the states
        states = tracker.getStates()
        assert disconnected_client_id not in states
        assert len(states) == len(mock_users) - 1
        
        # Clean up
        tracker.destroy()