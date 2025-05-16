# Collaboration Integration Tests for Jupyter Notebook v7

This directory contains integration tests for the real-time collaborative editing features in Jupyter Notebook v7. These tests verify that the collaboration components work together correctly in realistic multi-user scenarios.

## Test Files

- `test_locks_integration.py`: Tests the cell locking mechanism in a multi-user environment, verifying that users can acquire exclusive locks on cells, preventing editing conflicts while allowing concurrent work on different cells.

- `test_presence_integration.py`: Tests the user presence awareness system across multiple clients, ensuring that cursor positions, selections, and user status are correctly synchronized.

- `test_comments_integration.py`: Tests the comment system in a multi-user environment, verifying that users can create, view, reply to, and resolve comments on specific cells.

- `test_permissions_integration.py`: Tests the permission system in a multi-user environment, ensuring that access controls are correctly enforced, preventing unauthorized modifications while allowing permitted actions.

- `test_history_integration.py`: Tests the version history system in a multi-user environment, verifying that document changes are properly recorded with user attribution and can be used for document restoration.

- `test_sync_integration.py`: Tests end-to-end document synchronization across multiple clients, ensuring that changes to notebook cells propagate correctly between clients and that concurrent editing scenarios are handled properly.

- `test_resilience_integration.py`: Tests the system's resilience to network issues, server restarts, and other disruptions, ensuring that collaboration can continue or recover properly after interruptions.

## Test Fixtures

Common test fixtures are defined in `conftest.py` and provide:

- A Jupyter server with collaboration enabled
- Test notebook documents
- WebSocket clients for multiple users
- Helper functions for sending and receiving WebSocket messages

## Running the Tests

To run the integration tests, use the following commands:

```bash
# Run all integration tests
pytest tests/integration/collab

# Run a specific test file
pytest tests/integration/collab/test_locks_integration.py

# Run a specific test
pytest tests/integration/collab/test_locks_integration.py::test_lock_acquisition_and_broadcast
```

## Testing Approach

The integration tests simulate realistic multi-user collaboration scenarios by:

1. **Creating a test server**: A Jupyter server with collaboration enabled is created for each test.

2. **Creating a test notebook**: A notebook document is created on the server for testing.

3. **Connecting multiple clients**: Multiple WebSocket clients connect to the server, each representing a different user.

4. **Simulating user actions**: The tests simulate user actions such as editing cells, acquiring locks, adding comments, etc.

5. **Verifying behavior**: The tests verify that the system behaves correctly, with changes propagating to all clients and conflicts being resolved appropriately.

## Test Scenarios

The integration tests cover the following key scenarios:

### Lock Management

- Acquiring and releasing locks on cells
- Lock conflict resolution when multiple users attempt to lock the same cell
- Automatic lock release after timeout or disconnection
- Administrative override of locks

### User Presence

- Tracking and displaying user cursor positions and selections
- Updating user status (active, idle, offline)
- Cleaning up presence information when users disconnect

### Comment System

- Creating and viewing comments on specific cells
- Replying to existing comments
- Resolving comment threads
- Notifying users of new comments

### Permission Management

- Enforcing role-based access control (view, edit, admin)
- Handling permission changes and propagation
- Integrating with authentication systems

### Document Synchronization

- Synchronizing changes between multiple clients
- Handling concurrent edits to different cells
- Resolving conflicts during simultaneous editing of the same cell
- Verifying document state consistency after synchronization

### Resilience

- Handling network interruptions
- Recovering from server restarts
- Dealing with client disconnection and reconnection
- Maintaining document consistency after disruptions