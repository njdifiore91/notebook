import os
import pytest
from tornado.httpclient import HTTPClientError
from tornado.websocket import websocket_connect
import json

from notebook.app import JupyterNotebookApp, NotebookHandler, TreeHandler
from notebook.collab.handlers import CollaborationHandler, CollaborationWebSocketHandler


@pytest.fixture
def notebooks(jp_create_notebook, notebookapp):
    nbpaths = (
        "notebook1.ipynb",
        "jlab_test_notebooks/notebook2.ipynb",
        "jlab_test_notebooks/level2/notebook3.ipynb",
    )
    for nb in nbpaths:
        jp_create_notebook(nb)
    return nbpaths


@pytest.fixture
def collaboration_config(notebookapp):
    """Fixture to ensure collaboration is enabled for tests"""
    app = notebookapp
    app.collaboration_enabled = True
    app.collaboration_backend = "memory"  # Use in-memory backend for tests
    app.collaboration_auth_mode = "token"  # Use token auth for tests
    return app


async def test_notebook_handler(notebooks, jp_fetch):
    for nbpath in notebooks:
        r = await jp_fetch("/", nbpath)
        assert r.code == 200
        # Check that the lab template is loaded
        html = r.body.decode()
        assert "Jupyter Notebook" in html

        r = await jp_fetch("/notebooks", nbpath)
        assert r.code == 200
        # Check that the lab template is loaded
        html = r.body.decode()
        assert "Jupyter Notebook" in html

    redirected_url = None

    def redirect(self, url):
        nonlocal redirected_url
        redirected_url = url

    NotebookHandler.redirect = redirect
    await jp_fetch("notebooks", "jlab_test_notebooks")
    assert redirected_url == "/a%40b/tree/jlab_test_notebooks"


async def test_tree_handler(notebooks, notebookapp, jp_fetch):
    app: JupyterNotebookApp = notebookapp
    r = await jp_fetch("tree", "jlab_test_notebooks")
    assert r.code == 200

    # Check that the tree template is loaded
    html = r.body.decode()
    assert "<title>Home</title>" in html

    redirected_url = None

    def redirect(self, url):
        nonlocal redirected_url
        redirected_url = url

    TreeHandler.redirect = redirect
    await jp_fetch("tree", "notebook1.ipynb")
    assert redirected_url == "/a%40b/notebooks/notebook1.ipynb"

    with open(os.path.join(app.serverapp.root_dir, "foo.txt"), "w") as fid:
        fid.write("hello")

    await jp_fetch("tree", "foo.txt")
    assert redirected_url == "/a%40b/files/foo.txt"

    with pytest.raises(HTTPClientError):
        await jp_fetch("tree", "does_not_exist.ipynb")


async def test_console_handler(notebookapp, jp_fetch):
    r = await jp_fetch("consoles", "foo")
    assert r.code == 200
    html = r.body.decode()
    assert "- Console</title>" in html


async def test_terminals_handler(notebookapp, jp_fetch):
    r = await jp_fetch("terminals", "foo")
    assert r.code == 200
    html = r.body.decode()
    assert "- Terminal</title>" in html


async def test_edit_handler(notebooks, jp_fetch):
    r = await jp_fetch("edit", "notebook1.ipynb")
    assert r.code == 200
    html = r.body.decode()
    assert "- Edit</title>" in html


async def test_app(notebookapp):
    app: JupyterNotebookApp = notebookapp
    assert app.static_dir
    assert app.templates_dir
    assert app.app_settings_dir
    assert app.schemas_dir
    assert app.user_settings_dir
    assert app.workspaces_dir


async def test_collaboration_config_options(notebookapp):
    """Test that collaboration configuration options are properly loaded"""
    app: JupyterNotebookApp = notebookapp
    
    # Test default values
    assert hasattr(app, 'collaboration_enabled')
    assert hasattr(app, 'collaboration_backend')
    assert hasattr(app, 'collaboration_auth_mode')
    assert hasattr(app, 'collaboration_session_timeout')
    
    # Test setting values
    app.collaboration_enabled = True
    app.collaboration_backend = "database"
    app.collaboration_auth_mode = "jwt"
    app.collaboration_session_timeout = 3600
    
    assert app.collaboration_enabled is True
    assert app.collaboration_backend == "database"
    assert app.collaboration_auth_mode == "jwt"
    assert app.collaboration_session_timeout == 3600


async def test_collaboration_handler(notebooks, jp_fetch, collaboration_config):
    """Test the collaboration API endpoints"""
    # Test collaboration status endpoint
    r = await jp_fetch("api/collaboration/v1/status")
    assert r.code == 200
    status = json.loads(r.body.decode())
    assert status["enabled"] is True
    
    # Test collaboration sessions endpoint
    r = await jp_fetch("api/collaboration/v1/sessions")
    assert r.code == 200
    sessions = json.loads(r.body.decode())
    assert "sessions" in sessions
    
    # Test creating a collaboration session for a notebook
    data = {"document_id": "notebook1.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    assert r.code == 201
    session = json.loads(r.body.decode())
    assert "session_id" in session
    assert session["document_id"] == "notebook1.ipynb"
    
    # Get the created session
    session_id = session["session_id"]
    r = await jp_fetch(f"api/collaboration/v1/sessions/{session_id}")
    assert r.code == 200
    session_details = json.loads(r.body.decode())
    assert session_details["session_id"] == session_id
    assert session_details["document_id"] == "notebook1.ipynb"
    assert "created_at" in session_details
    assert "active_users" in session_details


async def test_collaboration_permissions(notebooks, jp_fetch, collaboration_config):
    """Test the collaboration permissions API endpoints"""
    # Create a session first
    data = {"document_id": "notebook1.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Test getting permissions for a document
    r = await jp_fetch(f"api/collaboration/v1/permissions/{document_id}")
    assert r.code == 200
    permissions = json.loads(r.body.decode())
    assert "permissions" in permissions
    
    # Test granting a permission
    permission_data = {
        "user_id": "test_user",
        "role": "editor"
    }
    r = await jp_fetch(f"api/collaboration/v1/permissions/{document_id}", 
                      method="POST", 
                      body=json.dumps(permission_data))
    assert r.code == 201
    permission = json.loads(r.body.decode())
    assert permission["user_id"] == "test_user"
    assert permission["role"] == "editor"
    assert "id" in permission
    
    # Test updating a permission
    permission_id = permission["id"]
    update_data = {"role": "commenter"}
    r = await jp_fetch(f"api/collaboration/v1/permissions/{document_id}/{permission_id}", 
                      method="PUT", 
                      body=json.dumps(update_data))
    assert r.code == 200
    updated_permission = json.loads(r.body.decode())
    assert updated_permission["role"] == "commenter"
    
    # Test deleting a permission
    r = await jp_fetch(f"api/collaboration/v1/permissions/{document_id}/{permission_id}", 
                      method="DELETE")
    assert r.code == 204
    
    # Verify it's deleted
    r = await jp_fetch(f"api/collaboration/v1/permissions/{document_id}")
    permissions = json.loads(r.body.decode())["permissions"]
    assert not any(p["id"] == permission_id for p in permissions)


async def test_collaboration_comments(notebooks, jp_fetch, collaboration_config):
    """Test the collaboration comments API endpoints"""
    # Create a session first
    data = {"document_id": "notebook1.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Test getting comments for a document
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}")
    assert r.code == 200
    comments = json.loads(r.body.decode())
    assert "threads" in comments
    
    # Test creating a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This is a test comment"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    assert r.code == 201
    thread = json.loads(r.body.decode())
    assert thread["cell_id"] == "cell-1"
    assert "id" in thread
    assert "comments" in thread
    assert len(thread["comments"]) == 1
    assert thread["comments"][0]["content"] == "This is a test comment"
    
    # Test adding a reply to a thread
    thread_id = thread["id"]
    reply_data = {"content": "This is a reply"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}", 
                      method="POST", 
                      body=json.dumps(reply_data))
    assert r.code == 201
    comment = json.loads(r.body.decode())
    assert comment["content"] == "This is a reply"
    assert "id" in comment
    
    # Test resolving a thread
    resolve_data = {"status": "resolved"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/status", 
                      method="PUT", 
                      body=json.dumps(resolve_data))
    assert r.code == 200
    updated_thread = json.loads(r.body.decode())
    assert updated_thread["status"] == "resolved"


async def test_collaboration_websocket(notebooks, jp_fetch, collaboration_config, jp_ws_url):
    """Test the collaboration WebSocket endpoints"""
    # Create a session first
    data = {"document_id": "notebook1.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    session_id = session["session_id"]
    
    # Connect to the collaboration WebSocket
    ws_url = f"{jp_ws_url}/collaboration/{session_id}"
    ws = await websocket_connect(ws_url)
    
    # Test sending and receiving a message
    test_message = {"type": "sync", "data": {"test": "data"}}
    await ws.write_message(json.dumps(test_message))
    
    # Should receive an acknowledgment or echo back
    response = await ws.read_message()
    response_data = json.loads(response)
    assert "type" in response_data
    
    # Test awareness protocol
    awareness_message = {
        "type": "awareness", 
        "data": {
            "user": {
                "name": "Test User",
                "color": "#ff0000",
                "status": "active"
            },
            "cursor": {"cell": "cell-1", "position": 10}
        }
    }
    await ws.write_message(json.dumps(awareness_message))
    
    # Should receive an awareness update acknowledgment
    response = await ws.read_message()
    response_data = json.loads(response)
    assert response_data["type"] == "awareness-ack"
    
    # Close the WebSocket connection
    ws.close()


async def test_collaboration_integration(notebooks, jp_fetch, collaboration_config):
    """Test the integration of collaboration components with the main application"""
    # Test that collaboration components are properly initialized
    r = await jp_fetch("api/collaboration/v1/status")
    status = json.loads(r.body.decode())
    assert status["enabled"] is True
    assert "version" in status
    assert "backend" in status
    assert status["backend"] == "memory"
    
    # Test that notebook handler includes collaboration scripts when collaboration is enabled
    for nbpath in notebooks:
        r = await jp_fetch("/notebooks", nbpath)
        assert r.code == 200
        html = r.body.decode()
        # Check for collaboration-related elements in the HTML
        assert "collaboration-enabled" in html
        
    # Test that the collaboration API is accessible from the notebook interface
    r = await jp_fetch("/notebooks", "notebook1.ipynb")
    html = r.body.decode()
    assert "/api/collaboration/v1/" in html
    
    # Test that collaboration components are properly registered with the application
    app = collaboration_config
    assert hasattr(app, "collaboration_manager")
    assert app.collaboration_manager is not None