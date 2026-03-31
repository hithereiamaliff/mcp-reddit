# Missing Parameters & Feature Gaps

This document tracks missing parameters, unsupported features, and potential improvements for the MCP Reddit server tools.

---

## `fetch_reddit_hot_threads`

### Current Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `subreddit` | string | Yes | — | Name of the subreddit (without `r/` prefix) |
| `limit` | integer | No | 10 | Number of posts to fetch |
| `sort` | string | No | `hot` | Sort order: `hot`, `new`, `top`, `rising`, `controversial` |
| `time_filter` | string | No | `day` | Time filter for `top`/`controversial`: `hour`, `day`, `week`, `month`, `year`, `all` |
| `after` | string | No | — | Pagination cursor to fetch results after (e.g. `t3_abc123`) |
| `before` | string | No | — | Pagination cursor to fetch results before (e.g. `t3_abc123`) |
| `client_id` | string | No | env var | Reddit API client ID |
| `client_secret` | string | No | env var | Reddit API client secret |

### ~~Missing: Sort Parameter~~ IMPLEMENTED

Sort parameter added with support for `hot`, `new`, `top`, `rising`, `controversial`. Time filter parameter added for `top` and `controversial` sorts.

> **Note:** `best` is not available for subreddit listings — it is a front-page only endpoint in Reddit's API.

### ~~Missing: Pagination (`after` / `before`)~~ IMPLEMENTED

Cursor-based pagination added via `after` and `before` parameters. Pagination cursors are only emitted in the response when Reddit confirms more pages exist (`has_after`/`has_before`).

---

## `fetch_reddit_post_content`

### Current Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `post_id` | string | Yes | — | Reddit post ID |
| `comment_limit` | integer | No | 20 | Number of top-level comments to fetch |
| `comment_depth` | integer | No | 3 | Maximum depth of comment tree to traverse |
| `comment_sort` | string | No | `top` | Comment sort: `top`, `best`, `new`, `controversial`, `old`, `qa` |
| `client_id` | string | No | env var | Reddit API client ID |
| `client_secret` | string | No | env var | Reddit API client secret |

### ~~Missing: Comment Sort~~ IMPLEMENTED

Comment sort parameter added with support for `top`, `best`, `new`, `controversial`, `old`, `qa`. The `best` value maps to Reddit API's `confidence` sort internally, while the default remains `top` for backward compatibility with existing callers.

---

## ~~General Missing Features~~ IMPLEMENTED

### ~~Search Tool~~ IMPLEMENTED as `search_reddit`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query |
| `subreddit` | string | `""` | Subreddit to search within (empty = all of Reddit) |
| `sort` | string | `relevance` | Sort: `relevance`, `hot`, `top`, `new`, `comments` |
| `time_filter` | string | `all` | Time filter: `hour`, `day`, `week`, `month`, `year`, `all` |
| `limit` | int | 10 | Number of results |

### ~~User Profile Tool~~ IMPLEMENTED as `fetch_user_profile`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `username` | string | *required* | Reddit username (without `u/` prefix) |
| `content_type` | string | `overview` | Content type: `overview`, `submitted`, `comments` |
| `sort` | string | `new` | Sort: `hot`, `new`, `top`, `controversial` |
| `limit` | int | 10 | Number of items to fetch |

### ~~Subreddit Info Tool~~ IMPLEMENTED as `fetch_subreddit_info`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subreddit` | string | *required* | Subreddit name (without `r/` prefix) |

Returns subscriber count, description, rules, accepted post types, NSFW/quarantine status, and more.

---

*Last updated: 2026-03-31*
