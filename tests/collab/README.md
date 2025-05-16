# Collaboration Tests for Jupyter Notebook v7

This directory contains tests for the real-time collaborative editing features in Jupyter Notebook v7. These features enable multiple users to simultaneously edit notebook documents with conflict-free synchronization, user presence awareness, cell-level locking, and more.

## Test Structure

The tests are organized into two main categories:

1. **Unit Tests** (in `tests/collab/`): Test individual components of the collaboration system in isolation, with mocked dependencies.

2. **Integration Tests** (in `tests/integration/collab/`): Test the interaction between multiple components and simulate real-world usage scenarios with multiple clients.

## Test Files

### Unit Tests

- `test_locks.py`: Tests the cell-level locking mechanism that prevents editing conflicts.
- `test_awareness.py`: Tests the user presence awareness system that tracks cursor positions and selections.
- `test_comments.py`: Tests the comment and review system for discussing specific cells.
- `test_permissions.py`: Tests the permission system for controlling access to collaborative notebooks.
- `test_history.py`: Tests the version history and change tracking system.
- `test_yjs_integration.py`: Tests the integration between Jupyter's document model and the Yjs CRDT framework.
- `test_collab_persistence.py`: Tests the persistence layer for collaborative editing state.
- `test_collab_handlers.py`: Tests the server-side WebSocket handlers for collaborative editing.

### Integration Tests

- `test_locks_integration.py`: Tests the cell locking mechanism in a multi-user environment.
- `test_presence_integration.py`: Tests the user presence awareness system across multiple clients.
- `test_comments_integration.py`: Tests the comment system in a multi-user environment.
- `test_permissions_integration.py`: Tests the permission system in a multi-user environment.
- `test_history_integration.py`: Tests the version history system in a multi-user environment.
- `test_sync_integration.py`: Tests end-to-end document synchronization across multiple clients.
- `test_resilience_integration.py`: Tests the system's resilience to network issues and server restarts.

## Running the Tests

To run the collaboration tests, use the following commands:

```bash
# Run all collaboration tests
pytest tests/collab tests/integration/collab

# Run only unit tests
pytest tests/collab

# Run only integration tests
pytest tests/integration/collab

# Run a specific test file
pytest tests/collab/test_locks.py

# Run a specific test
pytest tests/collab/test_locks.py::test_lock_acquisition
```

## Test Fixtures

Common test fixtures are defined in `conftest.py` files in both the unit test and integration test directories. These fixtures provide:

- Mock Yjs documents, maps, arrays, and text objects
- Mock WebSocket clients for simulating multiple users
- Mock collaboration managers and lock managers
- Test notebook documents and cells
- Helper functions for sending and receiving WebSocket messages

## Testing Approach

### Unit Testing

Unit tests use mocked dependencies to isolate the component being tested. For example, when testing the lock manager, we mock the Yjs document and WebSocket clients to focus on the lock manager's behavior.

### Integration Testing

Integration tests use a real Jupyter server with the collaboration extension enabled, and create multiple WebSocket clients to simulate multiple users collaborating on the same notebook. These tests verify that the components work together correctly in realistic scenarios.

### Yjs CRDT Testing

Testing the Yjs CRDT (Conflict-free Replicated Data Type) functionality requires special consideration:

1. **Deterministic Conflict Resolution**: Tests verify that concurrent edits are merged consistently across all clients.

2. **State Synchronization**: Tests ensure that document state is properly synchronized between clients, even after disconnections.

3. **Awareness Protocol**: Tests validate that user presence information is correctly shared among clients.

4. **Performance**: Tests check that the system performs well with large documents and many concurrent edits.

## Adding New Tests

When adding new tests for collaboration features, consider the following guidelines:

1. **Unit Tests**: Add unit tests for new components or functionality, mocking dependencies as needed.

2. **Integration Tests**: Add integration tests for new user workflows or interaction patterns.

3. **Edge Cases**: Test edge cases such as disconnections, concurrent edits, and permission conflicts.

4. **Performance**: Test performance with large documents and many concurrent users.

5. **Resilience**: Test the system's resilience to network issues, server restarts, and other disruptions.