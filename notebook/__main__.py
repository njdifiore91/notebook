"""CLI entry point for notebook."""

import sys
import argparse
from typing import List, Optional

from notebook.app import main


def parse_collaboration_args(args: Optional[List[str]] = None) -> List[str]:
    """
    Parse collaboration-specific command line arguments and return them as a list
    to be passed to the main function.
    
    Args:
        args: Command line arguments to parse. If None, sys.argv[1:] is used.
        
    Returns:
        List of processed arguments to pass to the main function.
    """
    parser = argparse.ArgumentParser(add_help=False)
    
    # Add collaboration-specific arguments
    collaboration_group = parser.add_argument_group('Collaboration options')
    collaboration_group.add_argument(
        '--collaborative', 
        action='store_true',
        help='Enable real-time collaborative editing features using Yjs CRDT framework'
    )
    
    # WebSocket configuration for collaboration
    collaboration_group.add_argument(
        '--CollaborationManager.websocket_max_message_size', 
        type=int,
        default=10 * 1024 * 1024,  # 10MB
        help='Maximum WebSocket message size in bytes (default: 10MB)'
    )
    collaboration_group.add_argument(
        '--CollaborationManager.ping_interval', 
        type=int,
        default=30,
        help='WebSocket ping interval in seconds to keep connections alive (default: 30)'
    )
    collaboration_group.add_argument(
        '--CollaborationManager.ping_timeout', 
        type=int,
        default=10,
        help='WebSocket ping timeout in seconds (default: 10)'
    )
    collaboration_group.add_argument(
        '--CollaborationManager.max_buffer_size', 
        type=int,
        default=100 * 1024 * 1024,  # 100MB
        help='Maximum buffer size in bytes (default: 100MB)'
    )
    collaboration_group.add_argument(
        '--CollaborationManager.compression_level', 
        type=int,
        choices=range(10),  # 0-9
        default=6,
        help='ZLIB compression level (0-9, default: 6)'
    )
    
    # Document synchronization configuration
    collaboration_group.add_argument(
        '--YDocExtension.document_save_delay', 
        type=float,
        default=1.0,
        help='Delay of inactivity (in seconds) after which a document is saved to disk (default: 1.0)'
    )
    collaboration_group.add_argument(
        '--YDocExtension.file_poll_interval', 
        type=float,
        default=1.0,
        help='Period (in seconds) to check for file changes on disk (default: 1.0)'
    )
    collaboration_group.add_argument(
        '--YDocExtension.document_cleanup_delay', 
        type=int,
        default=60,
        help='Delay (in seconds) to keep a document in memory after all clients disconnect (default: 60)'
    )
    
    # Parse known args and return them
    known_args, remaining_args = parser.parse_known_args(args)
    
    # Convert namespace to list of args to pass to main
    processed_args = []
    
    # Only add the args that were explicitly provided by the user
    for arg_name, arg_value in vars(known_args).items():
        if arg_name == 'collaborative' and arg_value:
            processed_args.append('--collaborative')
        elif arg_name.startswith('CollaborationManager.') or arg_name.startswith('YDocExtension.'):
            if parser.get_default(arg_name) != arg_value:
                processed_args.append(f'--{arg_name}={arg_value}')
    
    # Add remaining args
    processed_args.extend(remaining_args)
    
    return processed_args


if __name__ == "__main__":
    # Parse collaboration-specific arguments
    args = parse_collaboration_args(sys.argv[1:])
    
    # Pass processed args to main
    sys.exit(main(args))  # type:ignore[no-untyped-call]