from typing import Optional
from redditwarp.ASYNC import Client
from redditwarp.models.submission_ASYNC import (
    Submission,
    LinkPost,
    TextPost,
    GalleryPost,
    PollPost,
    CrosspostSubmission,
)
from redditwarp.models.comment_ASYNC import LooseComment
from fastmcp import FastMCP
import logging

mcp = FastMCP("Reddit MCP")
client = Client()
logging.getLogger().setLevel(logging.WARNING)
REDDIT_BASE_URL = "https://www.reddit.com"

# --- Validation constants for sort/filter parameters ---
VALID_SORTS = {"hot", "new", "top", "rising", "controversial"}
VALID_TIME_FILTERS = {"hour", "day", "week", "month", "year", "all"}
VALID_COMMENT_SORTS = {"best", "top", "new", "controversial", "old", "qa"}
VALID_SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}
VALID_USER_CONTENT_TYPES = {"overview", "submitted", "comments"}
VALID_USER_SORTS = {"hot", "new", "top", "controversial"}


def _normalize_choice(value, valid_choices: set[str], default: str) -> str:
    """Normalize a potentially invalid choice value to a safe default."""
    if not isinstance(value, str):
        return default
    normalized = value.strip().lower()
    return normalized if normalized in valid_choices else default


def _get_subreddit_submissions(reddit_client, subreddit: str, limit: int, sort: str, time_filter: str):
    """Map sort parameter to the correct redditwarp pull method.
    Falls back to 'hot' for unrecognized sort values."""
    sort = _normalize_choice(sort, VALID_SORTS, "hot")
    if sort == "hot":
        return reddit_client.p.subreddit.pull.hot(subreddit, limit)
    elif sort == "new":
        return reddit_client.p.subreddit.pull.new(subreddit, limit)
    elif sort == "top":
        tf = _normalize_choice(time_filter, VALID_TIME_FILTERS, "day")
        return reddit_client.p.subreddit.pull.top(subreddit, limit, time=tf)
    elif sort == "rising":
        return reddit_client.p.subreddit.pull.rising(subreddit, limit)
    elif sort == "controversial":
        tf = _normalize_choice(time_filter, VALID_TIME_FILTERS, "day")
        return reddit_client.p.subreddit.pull.controversial(subreddit, limit, time=tf)


def _map_comment_sort(sort: str) -> str:
    """Map user-friendly comment sort names to redditwarp values.
    Reddit API uses 'confidence' for what users know as 'best'."""
    sort = _normalize_choice(sort, VALID_COMMENT_SORTS, "top")
    if sort == "best":
        return "confidence"
    return sort


def _get_submission_link(submission) -> str:
    """Return a stable Reddit URL for a submission."""
    permalink = getattr(submission, "permalink", "")
    if not isinstance(permalink, str):
        return ""
    if permalink.startswith(("http://", "https://")):
        return permalink
    return f"{REDDIT_BASE_URL}{permalink}"


def _get_comment_link(comment) -> str:
    """Return a stable Reddit URL for a comment."""
    permalink_path = getattr(comment, "permalink_path", "")
    if not isinstance(permalink_path, str):
        return ""
    if permalink_path.startswith(("http://", "https://")):
        return permalink_path
    return f"{REDDIT_BASE_URL}{permalink_path}"


@mcp.tool()
async def fetch_reddit_hot_threads(
    subreddit: str,
    limit: int = 10,
    sort: str = "hot",
    time_filter: str = "day",
    after: str = "",
    before: str = ""
) -> str:
    """
    Fetch threads from a subreddit with flexible sorting and pagination

    Args:
        subreddit: Name of the subreddit (without r/ prefix)
        limit: Number of posts to fetch (default: 10)
        sort: Sort order - hot, new, top, rising, controversial (default: hot)
        time_filter: Time filter for top/controversial - hour, day, week, month, year, all (default: day)
        after: Pagination cursor to fetch results after (e.g. t3_abc123)
        before: Pagination cursor to fetch results before (e.g. t3_abc123)

    Returns:
        Human readable string containing list of post information with pagination cursors
    """
    try:
        # Get the async iterator for the chosen sort order
        iterator = _get_subreddit_submissions(client, subreddit, limit, sort, time_filter)

        # Set pagination cursor if provided
        if after or before:
            paginator = iterator.get_paginator()
            if after:
                paginator.after = after
            if before:
                paginator.before = before
                paginator.direction = False

        posts = []
        async for submission in iterator:
            post_info = (
                f"Title: {submission.title}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"Author: {submission.author_display_name or '[deleted]'}\n"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: {_get_submission_link(submission)}\n"
                f"---"
            )
            posts.append(post_info)

        if not posts:
            return f"No posts found in r/{subreddit} with sort '{sort}'."

        result = "\n\n".join(posts)

        # Append pagination cursors only when more pages exist
        paginator = iterator.get_paginator()
        has_pagination = False
        pagination_info = "\n\n--- Pagination ---"
        if paginator.has_after:
            pagination_info += f"\nnext_after: {paginator.after}"
            has_pagination = True
        if paginator.has_before:
            pagination_info += f"\nnext_before: {paginator.before}"
            has_pagination = True
        if has_pagination:
            result += pagination_info

        return result

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"

def _format_comment_tree(comment_node, depth: int = 0) -> str:
    """Helper method to recursively format comment tree with proper indentation"""
    comment = comment_node.value
    indent = "-- " * depth
    content = (
        f"{indent}* Author: {comment.author_display_name or '[deleted]'}\n"
        f"{indent}  Score: {comment.score}\n"
        f"{indent}  {comment.body}\n"
    )

    for child in comment_node.children:
        content += "\n" + _format_comment_tree(child, depth + 1)

    return content

@mcp.tool()
async def fetch_reddit_post_content(
    post_id: str,
    comment_limit: int = 20,
    comment_depth: int = 3,
    comment_sort: str = "top"
) -> str:
    """
    Fetch detailed content of a specific post

    Args:
        post_id: Reddit post ID
        comment_limit: Number of top level comments to fetch
        comment_depth: Maximum depth of comment tree to traverse
        comment_sort: Comment sort order - top, best, new, controversial, old, qa (default: top)

    Returns:
        Human readable string containing post content and comments tree
    """
    try:
        submission = await client.p.submission.fetch(post_id)

        content = (
            f"Title: {submission.title}\n"
            f"Score: {submission.score}\n"
            f"Author: {submission.author_display_name or '[deleted]'}\n"
            f"Type: {_get_post_type(submission)}\n"
            f"Content: {_get_content(submission)}\n"
        )

        mapped_sort = _map_comment_sort(comment_sort)
        comments = await client.p.comment_tree.fetch(post_id, sort=mapped_sort, limit=comment_limit, depth=comment_depth)
        if comments.children:
            content += "\nComments:\n"
            for comment in comments.children:
                content += "\n" + _format_comment_tree(comment)
        else:
            content += "\nNo comments found."

        return content

    except Exception as e:
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def search_reddit(
    query: str,
    subreddit: str = "",
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 10
) -> str:
    """
    Search Reddit for posts matching a query

    Args:
        query: Search query string
        subreddit: Subreddit to search within (empty string = all of Reddit)
        sort: Sort order - relevance, hot, top, new, comments (default: relevance)
        time_filter: Time filter - hour, day, week, month, year, all (default: all)
        limit: Number of results to return (default: 10)

    Returns:
        Human readable string containing search results
    """
    try:
        sort_val = _normalize_choice(sort, VALID_SEARCH_SORTS, "relevance")
        time_val = _normalize_choice(time_filter, VALID_TIME_FILTERS, "all")

        posts = []
        async for submission in client.p.submission.search(
            subreddit, query, limit, sort=sort_val, time=time_val
        ):
            post_info = (
                f"Title: {submission.title}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"Author: {submission.author_display_name or '[deleted]'}\n"
                f"Subreddit: r/{submission.subreddit.name}\n"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: {_get_submission_link(submission)}\n"
                f"---"
            )
            posts.append(post_info)

        if not posts:
            return f"No results found for query '{query}'."

        return f"Search results for '{query}':\n\n" + "\n\n".join(posts)

    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return f"An error occurred while searching: {str(e)}"


@mcp.tool()
async def fetch_subreddit_info(subreddit: str) -> str:
    """
    Fetch metadata, stats, and rules for a subreddit

    Args:
        subreddit: Name of the subreddit (without r/ prefix)

    Returns:
        Human readable string containing subreddit info and rules
    """
    try:
        sr = await client.p.subreddit.fetch_by_name(subreddit)

        info = (
            f"Subreddit: r/{sr.name}\n"
            f"Title: {sr.title}\n"
            f"Type: {sr.openness}\n"
            f"Subscribers: {sr.subscriber_count:,}\n"
            f"Active Users: {sr.viewing_count if sr.viewing_count >= 0 else 'N/A'}\n"
            f"Created: {sr.created_at.strftime('%Y-%m-%d')}\n"
            f"NSFW: {'Yes' if sr.nsfw else 'No'}\n"
            f"Quarantined: {'Yes' if sr.quarantined else 'No'}\n"
            f"\nDescription:\n{sr.public_description}\n"
        )

        submission_types = []
        if sr.accepts_text_submissions:
            submission_types.append("text")
        if sr.accepts_link_submissions:
            submission_types.append("link")
        if sr.accepts_gallery_submissions:
            submission_types.append("gallery")
        if sr.accepts_poll_submissions:
            submission_types.append("poll")
        info += f"\nAccepted Post Types: {', '.join(submission_types)}\n"

        # Fetch rules separately — failure should not discard metadata
        try:
            rules = await client.p.subreddit.get_rules(subreddit)
            if len(rules) > 0:
                info += f"\nRules ({len(rules)}):\n"
                for i, rule in enumerate(rules, 1):
                    info += f"\n{i}. {rule.short_name}\n"
                    if rule.description:
                        info += f"   {rule.description}\n"
            else:
                info += "\nNo rules found.\n"
        except Exception:
            info += "\nRules: Unable to fetch rules for this subreddit.\n"

        return info

    except Exception as e:
        logging.error(f"Subreddit info error: {str(e)}")
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def fetch_user_profile(
    username: str,
    content_type: str = "overview",
    sort: str = "new",
    limit: int = 10
) -> str:
    """
    Fetch a Reddit user's profile info and recent activity

    Args:
        username: Reddit username (without u/ prefix)
        content_type: Type of content - overview, submitted, comments (default: overview)
        sort: Sort order - hot, new, top, controversial (default: new)
        limit: Number of items to fetch (default: 10)

    Returns:
        Human readable string containing user profile and activity
    """
    try:
        user = await client.p.user.fetch_by_name(username)

        profile = (
            f"User: u/{user.name}\n"
            f"Post Karma: {user.post_karma:,}\n"
            f"Comment Karma: {user.comment_karma:,}\n"
            f"Total Karma: {user.total_karma:,}\n"
            f"Account Created: {user.created_at.strftime('%Y-%m-%d')}\n"
            f"Has Premium: {'Yes' if user.has_premium else 'No'}\n"
            f"Is Moderator: {'Yes' if user.is_a_subreddit_moderator else 'No'}\n"
        )

        ct = _normalize_choice(content_type, VALID_USER_CONTENT_TYPES, "overview")
        sort_val = _normalize_choice(sort, VALID_USER_SORTS, "new")

        items = []
        if ct == "overview":
            profile += f"\n--- Recent Activity (overview, sorted by {sort_val}) ---\n"
            async for item in client.p.user.pull.overview(username, limit, sort=sort_val):
                if isinstance(item, Submission):
                    items.append(
                        f"[Post] r/{item.subreddit.name}\n"
                        f"  Title: {item.title}\n"
                        f"  Score: {item.score}\n"
                        f"  Comments: {item.comment_count}\n"
                        f"  Type: {_get_post_type(item)}\n"
                        f"  Content: {_get_content(item)}\n"
                        f"  Link: {_get_submission_link(item)}\n"
                        f"  ---"
                    )
                elif isinstance(item, LooseComment):
                    body_preview = item.body[:300] + "..." if len(item.body) > 300 else item.body
                    items.append(
                        f"[Comment] r/{item.subreddit.name}\n"
                        f"  Score: {item.score}\n"
                        f"  {body_preview}\n"
                        f"  Link: {_get_comment_link(item)}\n"
                        f"  ---"
                    )

        elif ct == "submitted":
            profile += f"\n--- Posts (sorted by {sort_val}) ---\n"
            async for submission in client.p.user.pull.submitted(username, limit, sort=sort_val):
                items.append(
                    f"Title: {submission.title}\n"
                    f"Subreddit: r/{submission.subreddit.name}\n"
                    f"Score: {submission.score}\n"
                    f"Comments: {submission.comment_count}\n"
                    f"Type: {_get_post_type(submission)}\n"
                    f"Content: {_get_content(submission)}\n"
                    f"Link: {_get_submission_link(submission)}\n"
                    f"---"
                )

        elif ct == "comments":
            profile += f"\n--- Comments (sorted by {sort_val}) ---\n"
            async for comment in client.p.user.pull.comments(username, limit, sort=sort_val):
                body_preview = comment.body[:300] + "..." if len(comment.body) > 300 else comment.body
                items.append(
                    f"Subreddit: r/{comment.subreddit.name}\n"
                    f"Score: {comment.score}\n"
                    f"{body_preview}\n"
                    f"Link: {_get_comment_link(comment)}\n"
                    f"---"
                )

        if items:
            profile += "\n" + "\n\n".join(items)
        else:
            profile += "\nNo activity found."

        return profile

    except Exception as e:
        logging.error(f"User profile error: {str(e)}")
        return f"An error occurred: {str(e)}"


def _get_post_type(submission) -> str:
    """Helper method to determine post type"""
    if isinstance(submission, LinkPost):
        return 'link'
    elif isinstance(submission, TextPost):
        return 'text'
    elif isinstance(submission, GalleryPost):
        return 'gallery'
    elif isinstance(submission, PollPost):
        return 'poll'
    elif isinstance(submission, CrosspostSubmission):
        return 'crosspost'
    return 'unknown'

def _get_content(submission) -> Optional[str]:
    """Helper method to extract post content based on type"""
    if isinstance(submission, LinkPost):
        return submission.link
    elif isinstance(submission, TextPost):
        return submission.body
    elif isinstance(submission, GalleryPost):
        return str(submission.gallery_link)
    elif isinstance(submission, PollPost):
        return _get_submission_link(submission)
    elif isinstance(submission, CrosspostSubmission):
        if submission.original:
            return _get_submission_link(submission.original)
        return _get_submission_link(submission)
    return None
