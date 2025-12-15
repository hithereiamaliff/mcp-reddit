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
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse
from redditwarp.ASYNC import Client
from redditwarp.models.submission_ASYNC import LinkPost, TextPost, GalleryPost
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Default Reddit credentials from environment
DEFAULT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
DEFAULT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Initialize FastMCP server
mcp = FastMCP("Reddit MCP Server")

# Suppress verbose logging from redditwarp
logging.getLogger("redditwarp").setLevel(logging.WARNING)


def get_reddit_credentials(request: Request = None) -> tuple[str, str]:
    """
    Get Reddit API credentials from multiple sources (in order of priority):
    1. URL query parameters
    2. HTTP headers
    3. Environment variables
    """
    client_id = DEFAULT_CLIENT_ID
    client_secret = DEFAULT_CLIENT_SECRET
    
    if request:
        # Check URL query parameters first
        query_params = dict(request.query_params)
        if "client_id" in query_params:
            client_id = query_params["client_id"]
        if "client_secret" in query_params:
            client_secret = query_params["client_secret"]
        
        # Check headers (override query params if present)
        header_client_id = request.headers.get("X-Reddit-Client-ID")
        header_client_secret = request.headers.get("X-Reddit-Client-Secret")
        if header_client_id:
            client_id = header_client_id
        if header_client_secret:
            client_secret = header_client_secret
    
    return client_id, client_secret


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
    return 'unknown'


def _get_content(submission) -> Optional[str]:
    """Helper method to extract post content based on type"""
    if isinstance(submission, LinkPost):
        return submission.permalink
    elif isinstance(submission, TextPost):
        return submission.body
    elif isinstance(submission, GalleryPost):
        return str(submission.gallery_link)
    return None


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
async def fetch_reddit_hot_threads(subreddit: str, limit: int = 10, client_id: str = "", client_secret: str = "") -> str:
    """
    Fetch hot threads from a subreddit
    
    Args:
        subreddit: Name of the subreddit
        limit: Number of posts to fetch (default: 10)
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)
        
    Returns:
        Human readable string containing list of post information
    """
    try:
        # Use provided credentials or fall back to environment variables
        cid = client_id or DEFAULT_CLIENT_ID
        csecret = client_secret or DEFAULT_CLIENT_SECRET
        client = get_reddit_client(cid, csecret)
        
        posts = []
        async for submission in client.p.subreddit.pull.hot(subreddit, limit):
            post_info = (
                f"Title: {submission.title}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"Author: {submission.author_display_name or '[deleted]'}\n"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: https://reddit.com{submission.permalink}\n"
                f"---"
            )
            posts.append(post_info)
            
        return "\n\n".join(posts)

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def fetch_reddit_post_content(post_id: str, comment_limit: int = 20, comment_depth: int = 3, client_id: str = "", client_secret: str = "") -> str:
    """
    Fetch detailed content of a specific post
    
    Args:
        post_id: Reddit post ID
        comment_limit: Number of top level comments to fetch
        comment_depth: Maximum depth of comment tree to traverse
        client_id: Reddit API client ID (optional, uses env var if not provided)
        client_secret: Reddit API client secret (optional, uses env var if not provided)

    Returns:
        Human readable string containing post content and comments tree
    """
    try:
        # Use provided credentials or fall back to environment variables
        cid = client_id or DEFAULT_CLIENT_ID
        csecret = client_secret or DEFAULT_CLIENT_SECRET
        client = get_reddit_client(cid, csecret)
        
        submission = await client.p.submission.fetch(post_id)
        
        content = (
            f"Title: {submission.title}\n"
            f"Score: {submission.score}\n"
            f"Author: {submission.author_display_name or '[deleted]'}\n"
            f"Type: {_get_post_type(submission)}\n"
            f"Content: {_get_content(submission)}\n"
        )

        comments = await client.p.comment_tree.fetch(post_id, sort='top', limit=comment_limit, depth=comment_depth)
        if comments.children:
            content += "\nComments:\n"
            for comment in comments.children:
                content += "\n" + _format_comment_tree(comment)
        else:
            content += "\nNo comments found."

        return content

    except Exception as e:
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


# Configure CORS middleware for browser-based clients
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "mcp-protocol-version",
            "mcp-session-id",
            "Authorization",
            "Content-Type",
            "X-Reddit-Client-ID",
            "X-Reddit-Client-Secret",
        ],
        expose_headers=["mcp-session-id"],
    )
]

# Create ASGI app with middleware
mcp_app = mcp.http_app(middleware=middleware)


# Create a wrapper Starlette app with health endpoint
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

async def health_check(request):
    """HTTP health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "server": "Reddit MCP Server",
        "version": "1.0.0",
        "transport": "streamable-http",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

# Mount MCP app under /mcp and add health endpoint
app = Starlette(
    routes=[
        Route("/health", health_check, methods=["GET"]),
        Mount("/mcp", app=mcp_app),
    ],
    middleware=middleware,
)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Reddit MCP Server on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
