"""
HTTP Server Entry Point for MCP Reddit Server
Streamable HTTP transport for VPS deployment with Nginx reverse proxy

Supports multiple API key input methods:
1. URL query parameters: ?client_id=xxx&client_secret=xxx
2. HTTP headers: X-Reddit-Client-ID, X-Reddit-Client-Secret
3. Environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
"""

import os
import logging
import signal
import atexit
from datetime import datetime
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
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Import analytics
from mcp_reddit.analytics import analytics, get_dashboard_html

# Import key service integration
from mcp_reddit.key_service import KeyServiceMiddleware, get_effective_credentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Graceful shutdown handler
def graceful_shutdown(signum=None, frame=None):
    """Save analytics on shutdown"""
    logger.info("Shutting down, saving analytics...")
    analytics.save()
    logger.info("Analytics saved successfully")

# Register shutdown handlers
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
atexit.register(analytics.save)

# Default Reddit credentials from environment
DEFAULT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
DEFAULT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Initialize FastMCP server
mcp = FastMCP("Reddit MCP Server")

# Suppress verbose logging from redditwarp
logging.getLogger("redditwarp").setLevel(logging.WARNING)
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



def get_reddit_client(client_id: str = "", client_secret: str = "") -> Client:
    """Create a Reddit client with optional credentials"""
    if client_id and client_secret:
        return Client.from_credentials(client_id, client_secret)
    return Client()


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


def _get_subreddit_submissions(client, subreddit: str, limit: int, sort: str, time_filter: str):
    """Map sort parameter to the correct redditwarp pull method.
    Falls back to 'hot' for unrecognized sort values."""
    sort = _normalize_choice(sort, VALID_SORTS, "hot")
    if sort == "hot":
        return client.p.subreddit.pull.hot(subreddit, limit)
    elif sort == "new":
        return client.p.subreddit.pull.new(subreddit, limit)
    elif sort == "top":
        tf = _normalize_choice(time_filter, VALID_TIME_FILTERS, "day")
        return client.p.subreddit.pull.top(subreddit, limit, time=tf)
    elif sort == "rising":
        return client.p.subreddit.pull.rising(subreddit, limit)
    elif sort == "controversial":
        tf = _normalize_choice(time_filter, VALID_TIME_FILTERS, "day")
        return client.p.subreddit.pull.controversial(subreddit, limit, time=tf)


def _map_comment_sort(sort: str) -> str:
    """Map user-friendly comment sort names to redditwarp values.
    Reddit API uses 'confidence' for what users know as 'best'."""
    sort = _normalize_choice(sort, VALID_COMMENT_SORTS, "top")
    if sort == "best":
        return "confidence"
    return sort


@mcp.tool()
async def fetch_reddit_hot_threads(
    subreddit: str,
    limit: int = 10,
    sort: str = "hot",
    time_filter: str = "day",
    after: str = "",
    before: str = "",
    client_id: str = "",
    client_secret: str = ""
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
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing list of post information with pagination cursors
    """
    # Track tool call
    analytics.track_tool_call("fetch_reddit_hot_threads", "mcp-client", "Claude Desktop")

    try:
        cid, csecret = get_effective_credentials(
            client_id, client_secret, DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET
        )
        client = get_reddit_client(cid, csecret)

        # Get the async iterator for the chosen sort order
        iterator = _get_subreddit_submissions(client, subreddit, limit, sort, time_filter)

        # Set pagination cursor if provided
        if after or before:
            paginator = iterator.get_paginator()
            if after:
                paginator.after = after
            if before:
                paginator.before = before
                paginator.direction = False  # reverse direction for 'before'

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
        logger.error(f"An error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def fetch_reddit_post_content(
    post_id: str,
    comment_limit: int = 20,
    comment_depth: int = 3,
    comment_sort: str = "top",
    client_id: str = "",
    client_secret: str = ""
) -> str:
    """
    Fetch detailed content of a specific post

    Args:
        post_id: Reddit post ID
        comment_limit: Number of top level comments to fetch
        comment_depth: Maximum depth of comment tree to traverse
        comment_sort: Comment sort order - top, best, new, controversial, old, qa (default: top)
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing post content and comments tree
    """
    # Track tool call
    analytics.track_tool_call("fetch_reddit_post_content", "mcp-client", "Claude Desktop")

    try:
        # Use provided credentials or fall back to environment variables
        cid, csecret = get_effective_credentials(
            client_id, client_secret, DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET
        )
        client = get_reddit_client(cid, csecret)

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
    limit: int = 10,
    client_id: str = "",
    client_secret: str = ""
) -> str:
    """
    Search Reddit for posts matching a query

    Args:
        query: Search query string
        subreddit: Subreddit to search within (empty string = all of Reddit)
        sort: Sort order - relevance, hot, top, new, comments (default: relevance)
        time_filter: Time filter - hour, day, week, month, year, all (default: all)
        limit: Number of results to return (default: 10)
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing search results
    """
    analytics.track_tool_call("search_reddit", "mcp-client", "Claude Desktop")

    try:
        cid, csecret = get_effective_credentials(
            client_id, client_secret, DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET
        )
        client = get_reddit_client(cid, csecret)

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
        logger.error(f"Search error: {str(e)}")
        return f"An error occurred while searching: {str(e)}"


@mcp.tool()
async def fetch_subreddit_info(
    subreddit: str,
    client_id: str = "",
    client_secret: str = ""
) -> str:
    """
    Fetch metadata, stats, and rules for a subreddit

    Args:
        subreddit: Name of the subreddit (without r/ prefix)
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing subreddit info and rules
    """
    analytics.track_tool_call("fetch_subreddit_info", "mcp-client", "Claude Desktop")

    try:
        cid, csecret = get_effective_credentials(
            client_id, client_secret, DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET
        )
        client = get_reddit_client(cid, csecret)

        sr = await client.p.subreddit.fetch_by_name(subreddit)

        # Build subreddit metadata
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

        # Accepted submission types
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
        logger.error(f"Subreddit info error: {str(e)}")
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def fetch_user_profile(
    username: str,
    content_type: str = "overview",
    sort: str = "new",
    limit: int = 10,
    client_id: str = "",
    client_secret: str = ""
) -> str:
    """
    Fetch a Reddit user's profile info and recent activity

    Args:
        username: Reddit username (without u/ prefix)
        content_type: Type of content - overview, submitted, comments (default: overview)
        sort: Sort order - hot, new, top, controversial (default: new)
        limit: Number of items to fetch (default: 10)
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing user profile and activity
    """
    analytics.track_tool_call("fetch_user_profile", "mcp-client", "Claude Desktop")

    try:
        cid, csecret = get_effective_credentials(
            client_id, client_secret, DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET
        )
        client = get_reddit_client(cid, csecret)

        # Fetch user info
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

        # Validate parameters
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
                # Skip unknown types gracefully

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
        logger.error(f"User profile error: {str(e)}")
        return f"An error occurred: {str(e)}"


# Health check resource
@mcp.resource("health://status")
def get_health_status() -> str:
    """Provide server health status"""
    return f"""{{
  "status": "healthy",
  "server": "Reddit MCP Server",
  "version": "1.0.0",
  "transport": "streamable-http",
  "timestamp": "{datetime.utcnow().isoformat()}Z"
}}"""


# CORS settings shared by both inner MCP app and outer Starlette app
_cors_kwargs = dict(
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "mcp-protocol-version",
        "mcp-session-id",
        "Authorization",
        "Content-Type",
        "X-Reddit-Client-ID",
        "X-Reddit-Client-Secret",
        "X-API-Key",
    ],
    expose_headers=["mcp-session-id"],
)

# Inner MCP app: CORS only (KeyServiceMiddleware is on the outer app)
cors_middleware = [Middleware(CORSMiddleware, **_cors_kwargs)]
mcp_app = mcp.http_app(middleware=cors_middleware)

# Outer app middleware: CORS (outermost) + KeyService (inner).
# CORS wraps KeyService, so 401/503 error responses still get CORS headers.
outer_middleware = [
    Middleware(CORSMiddleware, **_cors_kwargs),
    Middleware(KeyServiceMiddleware),
]


# Create a wrapper Starlette app with health and analytics endpoints
from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route, Mount

async def root_info(request):
    """Root endpoint - server info for Uptime Kuma and general discovery"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    analytics.track_request("GET", "/", client_ip, user_agent)
    
    return JSONResponse({
        "server": "Reddit MCP Server",
        "version": "1.0.0",
        "status": "online",
        "transport": "streamable-http",
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "analytics": "/analytics",
            "dashboard": "/analytics/dashboard"
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

async def health_check(request):
    """HTTP health check endpoint"""
    # Track request
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    analytics.track_request("GET", "/health", client_ip, user_agent)
    
    return JSONResponse({
        "status": "healthy",
        "server": "Reddit MCP Server",
        "version": "1.0.0",
        "transport": "streamable-http",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

async def analytics_json(request):
    """Analytics JSON endpoint"""
    return JSONResponse(analytics.get_summary())

async def analytics_dashboard(request):
    """Analytics HTML dashboard"""
    return HTMLResponse(get_dashboard_html())

async def analytics_import(request):
    """Import analytics from backup"""
    try:
        data = await request.json()
        analytics.import_data(data)
        return JSONResponse({
            "message": "Analytics imported successfully",
            "currentStats": {
                "totalRequests": analytics.get_data()["totalRequests"],
                "totalToolCalls": analytics.get_data()["totalToolCalls"],
            }
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# Create app with MCP lifespan for proper initialization
# Note: MCP app is mounted at root but handles /mcp path internally
# KeyServiceMiddleware rewrites /mcp/usr_xxx -> /mcp before routing reaches Mount
app = Starlette(
    routes=[
        Route("/", root_info, methods=["GET", "HEAD"]),
        Route("/health", health_check, methods=["GET", "HEAD"]),
        Route("/analytics", analytics_json, methods=["GET"]),
        Route("/analytics/", analytics_json, methods=["GET"]),
        Route("/analytics/dashboard", analytics_dashboard, methods=["GET"]),
        Route("/analytics/dashboard/", analytics_dashboard, methods=["GET"]),
        Route("/analytics/import", analytics_import, methods=["POST"]),
        Mount("/", app=mcp_app),
    ],
    middleware=outer_middleware,
    lifespan=mcp_app.lifespan,  # Required for FastMCP session manager
)


def run_http():
    """Entry point for both console script (mcp-reddit-http) and module execution."""
    import uvicorn
    logger.info(f"Starting Reddit MCP Server on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    run_http()
