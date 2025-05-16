# Comment and Review System

## Overview

The comment and review system in Jupyter Notebook v7 enables collaborative discussion directly within notebooks. This feature allows users to add, respond to, and resolve threaded comments on specific cells, facilitating review and feedback in collaborative work without modifying the notebook content itself.

With the comment system, you can:

- Add comments to specific cells
- Create threaded discussions with multiple participants
- Receive notifications when comments are added or updated
- Track and resolve comment threads
- View comment history even after cells have been modified

## Comment Data Model

The comment system is built on Jupyter Notebook v7's collaborative infrastructure using Yjs CRDT (Conflict-free Replicated Data Type) technology. Comments are synchronized in real-time across all connected users, ensuring that everyone sees the same comment threads regardless of when they join the session.

Each comment consists of:

- **Author**: The user who created the comment
- **Content**: The text of the comment (supports Markdown formatting)
- **Timestamp**: When the comment was created
- **Cell reference**: The specific cell the comment is attached to
- **Thread ID**: Identifier for the comment thread
- **Status**: Whether the thread is open or resolved
- **Metadata**: Additional information such as mentions, reactions, or attachments

Comment threads maintain their association with cells even as the notebook content changes, ensuring that discussions remain in context.

## Using the Comment System

### Adding a Comment

To add a new comment to a cell:

1. Select the cell you want to comment on
2. Click the comment icon in the cell toolbar or use the keyboard shortcut `Alt+C` (Windows/Linux) or `Option+C` (Mac)
3. Enter your comment in the comment panel that appears
4. Click "Submit" or press `Ctrl+Enter` to post the comment

![Adding a comment to a cell](../images/comment-add.png)

### Viewing Comments

Cells with comments display a comment indicator showing the number of comments. To view comments:

1. Click on the comment indicator in the cell margin
2. The comment panel will open, displaying all comments for that cell
3. Comments are displayed in chronological order within their threads

You can also access all comments in a notebook through the Comments tab in the collaboration panel, which shows all comment threads across the notebook.

### Replying to Comments

To reply to an existing comment:

1. Open the comment thread by clicking on the comment indicator
2. Click the "Reply" button on the comment you want to respond to
3. Enter your reply in the text field that appears
4. Click "Submit" or press `Ctrl+Enter` to post your reply

### Resolving Comment Threads

Once a discussion is complete, you can resolve the comment thread:

1. Open the comment thread
2. Click the "Resolve" button at the top of the thread
3. The thread will be marked as resolved and collapsed by default

Resolved threads can be reopened if further discussion is needed by clicking the "Reopen" button.

## Comment Notifications

The comment system includes notifications to keep collaborators informed about discussions:

- **Real-time notifications**: When someone adds a comment while you're viewing the notebook, a notification appears in the notification area
- **Mention notifications**: If someone mentions you using @username in a comment, you'll receive a special notification
- **Email notifications**: Optional email notifications can be configured for comments added when you're not actively viewing the notebook

## Configuration Options

The comment system can be configured through the Settings menu:

### User Preferences

```json
{
  "collaboration": {
    "comments": {
      "showResolvedThreads": true,
      "notificationsEnabled": true,
      "emailNotifications": false,
      "defaultSortOrder": "newest",
      "mentionCompletions": true
    }
  }
}
```

### Admin Configuration

Administrators can configure system-wide comment settings:

```json
{
  "collaboration": {
    "comments": {
      "enabled": true,
      "requirePermission": true,
      "maxThreadsPerCell": 10,
      "maxCommentsPerThread": 50,
      "retentionPeriod": "90days"
    }
  }
}
```

## Comment Persistence and Retrieval

Comments are stored in the Collaboration State Database and persist across sessions. This means:

- Comments remain available even after closing and reopening the notebook
- Comment history is preserved when the notebook is shared with others
- Comments can be exported and imported along with the notebook (optional feature)

To access historical comments:

1. Open the Comments tab in the collaboration panel
2. Use the filter options to show resolved threads or filter by date range
3. Search functionality allows you to find specific comments by content or author

## Example Workflow

Here's an example of how the comment system can be used in a collaborative review process:

1. **Author creates notebook**: A data scientist creates an analysis notebook
2. **Reviewer adds comments**: A reviewer adds comments on specific cells suggesting improvements or asking questions
3. **Author responds**: The original author replies to comments, either clarifying or making requested changes
4. **Discussion**: Multiple team members may join the discussion on specific points
5. **Resolution**: Once issues are addressed, comments are resolved
6. **Documentation**: Resolved comments serve as documentation of the review process and decisions made

## Permissions

Comment permissions are integrated with the notebook's collaboration permission system:

- **Viewers**: Can view comments but not add them
- **Commenters**: Can add and resolve comments but not edit notebook content
- **Editors**: Can add, resolve comments, and edit notebook content
- **Admins/Owners**: Have full control over all comments, including deletion

## Troubleshooting

### Common Issues

- **Comments not appearing**: Ensure you have at least "Commenter" permission and that comments are enabled for the notebook
- **Can't resolve a thread**: Only the thread creator, cell author, or users with Admin/Owner permissions can resolve threads by default
- **Missing notifications**: Check your notification settings in the Settings menu

### Recovering Comment History

If comments appear to be missing, you can attempt to recover them:

1. Open the Version History panel
2. Navigate to a previous version where the comments were present
3. Use the "Restore Comments" option to bring them back to the current version

## Keyboard Shortcuts

| Action | Windows/Linux | Mac |
|--------|--------------|-----|
| Add comment to selected cell | `Alt+C` | `Option+C` |
| Open comments panel | `Alt+Shift+C` | `Option+Shift+C` |
| Submit comment/reply | `Ctrl+Enter` | `Command+Enter` |
| Navigate between comments | `Up/Down Arrow` | `Up/Down Arrow` |
| Close comment panel | `Esc` | `Esc` |

## Conclusion

The comment and review system in Jupyter Notebook v7 provides a powerful way to collaborate on notebook documents. By separating discussions from the notebook content itself, teams can maintain clean, production-ready notebooks while still capturing important feedback, decisions, and context during the development process.