# User Profile Enhancements Plan

> Reference document for planned improvements to `fetch_user_profile` and new user-related tools in mcp-reddit.

## Table of Contents

- [Current State](#current-state)
- [Enhancement 1: Pagination Support](#enhancement-1-pagination-support)
- [Enhancement 2: Time Filter Support](#enhancement-2-time-filter-support)
- [Enhancement 3: Hidden Profile Workaround](#enhancement-3-hidden-profile-workaround-new-tool)
- [Implementation Notes](#implementation-notes)
- [Reddit "Content and Activity" Privacy Setting](#reddit-content-and-activity-privacy-setting)
- [Priority & Effort Estimates](#priority--effort-estimates)

---

## Current State

The existing `fetch_user_profile` tool (`src/mcp_reddit/reddit_fetcher.py`) supports:

| Feature | Status |
|---|---|
| Profile metadata (karma, account age, premium, mod status) | ✅ Working |
| `overview` — mixed posts + comments | ✅ Working |
| `submitted` — posts only | ✅ Working |
| `comments` — comments only | ✅ Working |
| Sort (`hot`, `new`, `top`, `controversial`) | ✅ Working |
| Limit (configurable item count) | ✅ Working |
| Pagination (`after`/`before` cursors) | ❌ Not implemented |
| Time filter (`hour`, `day`, `week`, `month`, `year`, `all`) | ❌ Not implemented |
| Bypass hidden profile (Content and Activity setting) | ❌ Not possible with current approach |

---

## Enhancement 1: Pagination Support

### What

Add `after` and `before` cursor parameters to `fetch_user_profile`, matching the pattern already used in `fetch_reddit_hot_threads`.

### Why

Currently, the tool can only fetch the first N items from a user's history. For users with extensive histories, there's no way to page through older content.

### How — redditwarp internals

The user pull methods (`client.p.user.pull.overview()`, `.submitted()`, `.comments()`) return an `ImpartedPaginatorChainingAsyncIterator`. The underlying paginator (`OverviewListingAsyncPaginator`, `SubmittedListingAsyncPaginator`, `CommentsListingAsyncPaginator`) all inherit from `ListingAsyncPaginator`, which has full cursor support:

```python
# ListingAsyncPaginator already has:
self.after: str = ''
self.before: str = ''
self.has_after: bool = True
self.has_before: bool = True
self.direction: bool = True  # True = forward, False = backward
```

### Implementation

```python
@mcp.tool()
async def fetch_user_profile(
    username: str,
    content_type: str = "overview",
    sort: str = "new",
    limit: int = 10,
    after: str = "",   # NEW
    before: str = ""   # NEW
) -> str:
    # ... profile metadata fetch stays the same ...

    # Get the iterator
    iterator = client.p.user.pull.overview(username, limit, sort=sort_val)

    # Set pagination cursor if provided
    if after or before:
        paginator = iterator.get_paginator()
        if after:
            paginator.after = after
        if before:
            paginator.before = before
            paginator.direction = False

    # ... iterate and collect items ...

    # Append pagination cursors at the end (same as fetch_reddit_hot_threads)
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
```

### Notes

- Apply the same pagination pattern to all three content types (`overview`, `submitted`, `comments`).
- Profile metadata should only be fetched on the first page (when no `after`/`before` is set), to avoid redundant API calls on subsequent pages.

---

## Enhancement 2: Time Filter Support

### What

Add a `time_filter` parameter to `fetch_user_profile` that works when `sort` is `top` or `controversial`.

### Why

Currently you can sort a user's posts by `top`, but there's no way to scope it to a time period (e.g., "top posts this month"). The Reddit API endpoint `/user/{name}/submitted?sort=top&t=week` supports the `t` parameter.

### How — redditwarp internals

The `Time` mixin exists at `redditwarp/pagination/paginators/listing/mixins/time_ASYNC.py` and adds the `t` query parameter. However, the user pull paginators (`OverviewListingAsyncPaginator`, etc.) only mix in `Sort`, **not** `Time`.

Two approaches:

#### Option A: Quick — inject `t` param manually (recommended)

The paginator has a `params` dict that gets included in requests. We can inject the time filter directly:

```python
iterator = client.p.user.pull.submitted(username, limit, sort=sort_val)
paginator = iterator.get_paginator()

if time_filter and sort_val in ("top", "controversial"):
    tf = _normalize_choice(time_filter, VALID_TIME_FILTERS, "all")
    # Inject 't' param into the paginator's request params
    paginator.params = {**paginator.params, 't': tf}
```

#### Option B: Clean — create custom paginator subclasses

Create new paginator classes that mix in both `Sort` and `Time`:

```python
# In a new file or at the top of reddit_fetcher.py
from redditwarp.pagination.paginators.listing.mixins.sort_ASYNC import Sort
from redditwarp.pagination.paginators.listing.mixins.time_ASYNC import Time
from redditwarp.pagination.paginators.listing.submission_listing_async_paginator import SubmissionListingAsyncPaginator

class UserSubmittedWithTimeAsyncPaginator(
    Time[Submission],
    Sort[Submission],
    SubmissionListingAsyncPaginator,
): pass
```

Then use them directly instead of the built-in ones. This is cleaner but requires maintaining custom classes.

### Recommendation

**Use Option A** — it's simpler, doesn't require maintaining custom subclasses, and achieves the same result since the Reddit API handles the `t` parameter regardless of how it gets added to the request.

### Updated tool signature

```python
@mcp.tool()
async def fetch_user_profile(
    username: str,
    content_type: str = "overview",
    sort: str = "new",
    limit: int = 10,
    time_filter: str = "all",  # NEW
    after: str = "",
    before: str = ""
) -> str:
```

---

## Enhancement 3: Hidden Profile Workaround (New Tool)

### What

Add a new tool `search_user_posts` that uses Reddit's search endpoint with `author:username` to find a user's content even when their profile is hidden.

### Why — the problem

In June 2025, Reddit launched the **"Content and Activity"** privacy setting (under "Curate your profile"). Users can now:

- **Hide all** their public posts and comments from their profile.
- **Selectively hide** posts/comments from specific subreddits.
- This is per-community, not per-post.

**Impact on the API:** When a user hides their profile content, the API endpoints `/user/{name}/overview`, `/user/{name}/submitted`, and `/user/{name}/comments` return **empty results**. The `fetch_user_profile` tool would show "No activity found."

**Key detail:** The content is **not deleted** — it's only hidden from the profile view. The posts and comments still exist in the subreddits where they were posted. Reddit's search with `author:username` still returns them.

### How — implementation

Use the existing `client.p.submission.search()` method, which hits the `/search` endpoint rather than `/user/{name}/submitted`:

```python
@mcp.tool()
async def search_user_posts(
    username: str,
    query: str = "",
    subreddit: str = "",
    sort: str = "new",
    time_filter: str = "all",
    limit: int = 10
) -> str:
    """
    Search for a user's posts across Reddit using the search endpoint.
    This works even if the user has hidden their profile content
    via the 'Content and Activity' privacy setting.

    Args:
        username: Reddit username (without u/ prefix)
        query: Additional search terms (optional, empty = all posts by user)
        subreddit: Subreddit to search within (optional, empty = all of Reddit)
        sort: Sort order - relevance, hot, top, new, comments (default: new)
        time_filter: Time filter - hour, day, week, month, year, all (default: all)
        limit: Number of results to return (default: 10)

    Returns:
        Human readable string containing the user's posts found via search
    """
    try:
        # Build search query with author filter
        search_query = f"author:{username}"
        if query:
            search_query = f"{search_query} {query}"

        sort_val = _normalize_choice(sort, VALID_SEARCH_SORTS, "new")
        time_val = _normalize_choice(time_filter, VALID_TIME_FILTERS, "all")

        posts = []
        async for submission in client.p.submission.search(
            subreddit, search_query, limit, sort=sort_val, time=time_val
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
            return f"No posts found for user '{username}'" + (
                f" matching '{query}'" if query else ""
            ) + "."

        header = f"Posts by u/{username}"
        if query:
            header += f" matching '{query}'"
        if subreddit:
            header += f" in r/{subreddit}"

        return f"{header}:\n\n" + "\n\n".join(posts)

    except Exception as e:
        logging.error(f"User post search error: {str(e)}")
        return f"An error occurred while searching: {str(e)}"
```

### Limitations

- **Only finds posts (submissions), not comments.** Reddit's search API (`/search`) only indexes submissions, not comments. There is no reliable API-based way to find hidden comments by a specific user.
- **Search quality:** Reddit's search is known to be inconsistent — it may not return all results. Pagination can help retrieve more.
- **Rate limits:** Uses the same Reddit API quota as other tools.

### Alternative: comment search via subreddit

If you need to find a user's comments in a specific subreddit, one workaround is to fetch recent comments from the subreddit and filter by author. However, this is expensive (many API calls) and limited to recent comments. Not recommended as a general tool.

---

## Implementation Notes

### Files to modify

| File | Changes |
|---|---|
| `src/mcp_reddit/reddit_fetcher.py` | Update `fetch_user_profile` (pagination + time filter), add `search_user_posts` |
| `README.md` | Add `search_user_posts` to tool table, update `fetch_user_profile` parameters |
| `tests/` | Add tests for new parameters and new tool |

### Validation constants to add

```python
VALID_SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}  # Already exists
# No new constants needed — reuse existing ones
```

### README updates

Add to the tool table:

| Tool | Description |
|------|-------------|
| `search_user_posts` | Search for a user's posts via Reddit search (works even with hidden profiles) |

Add parameter table for `search_user_posts` and update `fetch_user_profile` parameter table with `time_filter`, `after`, `before`.

---

## Reddit "Content and Activity" Privacy Setting

### Summary

- **Launched:** June 3, 2025
- **Location:** Settings > Curate your profile > Content and Activity
- **Options:** Keep all public (default), hide all, or show only from specific subreddits
- **Scope:** Per-community, not per-post
- **API impact:** Profile listing endpoints (`/user/{name}/overview`, etc.) return empty when content is hidden
- **Workaround:** Search endpoint with `author:username` still finds posts
- **Moderator exception:** Mods can still see full history for 28 days after a user interacts with their community

### What's NOT hidden

- Username still appears next to posts/comments in the subreddits themselves
- Posts/comments are still searchable via Reddit search
- Profile metadata (karma, account age, etc.) remains visible
- Moderators retain 28-day access after user interaction

---

## Priority & Effort Estimates

| Enhancement | Priority | Effort | Dependencies |
|---|---|---|---|
| Pagination support | High | Low (~30 min) | None — pattern already exists in `fetch_reddit_hot_threads` |
| Time filter support | Medium | Low (~15 min) | None — param injection approach |
| `search_user_posts` tool | High | Medium (~1 hr) | None — uses existing `client.p.submission.search()` |
| README updates | Medium | Low (~15 min) | After all code changes |
| Tests | Medium | Medium (~1 hr) | After all code changes |

**Total estimated effort: ~3 hours**
