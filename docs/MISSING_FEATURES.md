# Missing Parameters & Feature Gaps

This document tracks missing parameters, unsupported features, and potential improvements for the MCP Reddit server tools.

---

## `fetch_reddit_hot_threads`

### Current Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `subreddit` | string | Yes | — | Name of the subreddit (without `r/` prefix) |
| `limit` | integer | No | 10 | Number of posts to fetch |
| `client_id` | string | No | env var | Reddit API client ID |
| `client_secret` | string | No | env var | Reddit API client secret |

### Missing: Sort Parameter

**Issue:** The tool currently only fetches Reddit's **"hot"** listing. There is no parameter to change the sort order.

Reddit supports the following listing endpoints, none of which are currently exposed:

| Sort | Reddit Endpoint | Description |
|------|-----------------|-------------|
| `hot` | `/r/{subreddit}/hot` | Default and currently the only supported sort |
| `new` | `/r/{subreddit}/new` | Latest posts by submission time |
| `top` | `/r/{subreddit}/top` | Top posts (requires `t` param: `hour`, `day`, `week`, `month`, `year`, `all`) |
| `rising` | `/r/{subreddit}/rising` | Posts gaining traction |
| `controversial` | `/r/{subreddit}/controversial` | Controversial posts (requires `t` param) |
| `best` | `/r/{subreddit}/best` | Reddit's "best" algorithm |

**Suggested implementation:** Add a `sort` parameter (default: `hot`) and a `time_filter` parameter (for `top` and `controversial` sorts).

```python
# Example proposed signature
def fetch_reddit_threads(
    subreddit: str,
    limit: int = 10,
    sort: str = "hot",        # new | hot | top | rising | controversial | best
    time_filter: str = "day", # hour | day | week | month | year | all (for top/controversial)
    client_id: str = "",
    client_secret: str = "",
) -> str:
```

### Missing: Pagination (`after` / `before`)

Reddit's listing API supports cursor-based pagination via `after` and `before` parameters (fullname of the last/first item, e.g. `t3_abc123`). Currently there's no way to paginate through results beyond the initial `limit`.

**Suggested parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `after` | string | Fullname of the item to fetch results after (e.g. `t3_abc123`) |
| `before` | string | Fullname of the item to fetch results before |

---

## `fetch_reddit_post_content`

### Current Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `post_id` | string | Yes | — | Reddit post ID |
| `comment_limit` | integer | No | 20 | Number of top-level comments to fetch |
| `comment_depth` | integer | No | 3 | Maximum depth of comment tree to traverse |
| `client_id` | string | No | env var | Reddit API client ID |
| `client_secret` | string | No | env var | Reddit API client secret |

### Missing: Comment Sort

Reddit supports sorting comments by `best`, `top`, `new`, `controversial`, `old`, `q&a`. Currently not exposed.

**Suggested parameter:**

| Parameter | Type | Default | Values |
|-----------|------|---------|--------|
| `comment_sort` | string | `best` | `best`, `top`, `new`, `controversial`, `old`, `qa` |

---

## General Missing Features

### Search Tool

No `search_reddit` tool exists yet. Reddit's search API (`/r/{subreddit}/search` or `/search`) supports:

| Parameter | Description |
|-----------|-------------|
| `q` | Search query |
| `sort` | `relevance`, `hot`, `top`, `new`, `comments` |
| `t` | Time filter: `hour`, `day`, `week`, `month`, `year`, `all` |
| `restrict_sr` | Restrict to subreddit (boolean) |
| `type` | `link`, `sr`, `user` |

### User Profile Tool

No tool to fetch a user's posts or comments (`/user/{username}/submitted`, `/user/{username}/comments`).

### Subreddit Info Tool

No tool to fetch subreddit metadata (`/r/{subreddit}/about`) — subscriber count, description, rules, etc.

---

*Last updated: 2026-03-30*
