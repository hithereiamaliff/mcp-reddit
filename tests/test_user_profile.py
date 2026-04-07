"""
Mocked async tests for fetch_user_profile enhancements (pagination, time filter,
conditional metadata skip) and the new search_user_posts tool.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build fake redditwarp objects
# ---------------------------------------------------------------------------

def _make_fake_user():
    user = MagicMock()
    user.name = "testuser"
    user.post_karma = 1000
    user.comment_karma = 2000
    user.total_karma = 3000
    user.created_at.strftime.return_value = "2020-01-01"
    user.has_premium = False
    user.is_a_subreddit_moderator = False
    return user


def _make_fake_submission(title="Test Post"):
    """Return a MagicMock that passes isinstance(item, Submission).

    We use spec_set=False so attributes not on TextPost's spec (like subreddit)
    can still be set. The spec is only used for isinstance checks.
    """
    from redditwarp.models.submission_ASYNC import TextPost
    subreddit = MagicMock()
    subreddit.name = "python"
    mock = MagicMock(spec=TextPost)
    mock.configure_mock(
        title=title,
        score=42,
        comment_count=5,
        subreddit=subreddit,
        body="post body",
        permalink="/r/python/comments/abc123/test_post/",
        author_display_name="testuser",
    )
    return mock


def _make_fake_comment(body="a comment"):
    from redditwarp.models.comment_ASYNC import LooseComment
    subreddit = MagicMock()
    subreddit.name = "python"
    mock = MagicMock(spec=LooseComment)
    mock.configure_mock(
        body=body,
        score=10,
        subreddit=subreddit,
        permalink_path="/r/python/comments/abc123/test_post/def456/",
    )
    return mock


class _FakeAsyncIterator:
    """An async iterator that yields pre-set items, with a controllable paginator."""

    def __init__(self, items, paginator=None):
        self._items = list(items)
        self._paginator = paginator or MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )

    def get_paginator(self):
        return self._paginator

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


# ---------------------------------------------------------------------------
# Tests for fetch_user_profile enhancements
# ---------------------------------------------------------------------------

class TestFetchUserProfileFirstPage:
    """On the first page (no after/before), metadata should be fetched."""

    @pytest.mark.asyncio
    async def test_first_page_includes_metadata(self):
        fake_user = _make_fake_user()
        fake_sub = _make_fake_submission()
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([fake_sub], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=fake_user)
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser")

        mock_client.p.user.fetch_by_name.assert_awaited_once_with("testuser")
        assert "Post Karma:" in result
        assert "Comment Karma:" in result
        assert "Account Created:" in result

    @pytest.mark.asyncio
    async def test_first_page_includes_section_header(self):
        fake_user = _make_fake_user()
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=fake_user)
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser")

        assert "--- Recent Activity (overview, sorted by new) ---" in result


class TestFetchUserProfilePagination:
    """Page 2+ (after/before set) should skip metadata fetch."""

    @pytest.mark.asyncio
    async def test_page2_skips_metadata(self):
        fake_sub = _make_fake_submission()
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([fake_sub], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser", after="t3_abc123")

        mock_client.p.user.fetch_by_name.assert_not_called()
        assert "Post Karma:" not in result
        assert "User: u/testuser" in result

    @pytest.mark.asyncio
    async def test_page2_still_includes_section_header(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser", after="t3_abc123")

        assert "--- Recent Activity (overview, sorted by new) ---" in result

    @pytest.mark.asyncio
    async def test_after_cursor_wired_to_paginator(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", after="t3_abc123")

        assert paginator.after == "t3_abc123"
        assert paginator.direction is True  # forward direction for 'after'

    @pytest.mark.asyncio
    async def test_before_cursor_wired_and_direction_reversed(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", before="t3_xyz789")

        assert paginator.before == "t3_xyz789"
        assert paginator.direction is False

    @pytest.mark.asyncio
    async def test_pagination_cursors_in_output(self):
        paginator = MagicMock(
            after="t3_next", before="", has_after=True, has_before=False,
            direction=True, params={},
        )
        fake_sub = _make_fake_submission()
        fake_iter = _FakeAsyncIterator([fake_sub], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser")

        assert "--- Pagination ---" in result
        assert "next_after: t3_next" in result

    @pytest.mark.asyncio
    async def test_no_pagination_section_when_no_more_pages(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_sub = _make_fake_submission()
        fake_iter = _FakeAsyncIterator([fake_sub], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            result = await fetch_user_profile("testuser")

        assert "--- Pagination ---" not in result


class TestFetchUserProfileTimeFilter:
    """Time filter should be injected into paginator params for top/controversial."""

    @pytest.mark.asyncio
    async def test_time_filter_injected_for_top_sort(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", sort="top", time_filter="week")

        assert paginator.params.get("t") == "week"

    @pytest.mark.asyncio
    async def test_time_filter_injected_for_controversial_sort(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", sort="controversial", time_filter="month")

        assert paginator.params.get("t") == "month"

    @pytest.mark.asyncio
    async def test_time_filter_ignored_for_new_sort(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", sort="new", time_filter="week")

        assert "t" not in paginator.params

    @pytest.mark.asyncio
    async def test_empty_time_filter_does_not_inject(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.overview.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", sort="top", time_filter="")

        assert "t" not in paginator.params


class TestFetchUserProfileContentTypes:
    """Pagination and time filter work across all content types."""

    @pytest.mark.asyncio
    async def test_submitted_branch_uses_pagination(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([_make_fake_submission()], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.submitted.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", content_type="submitted", after="t3_abc")

        assert paginator.after == "t3_abc"

    @pytest.mark.asyncio
    async def test_comments_branch_uses_pagination(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([_make_fake_comment()], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.pull.comments.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile("testuser", content_type="comments", after="t1_abc")

        assert paginator.after == "t1_abc"

    @pytest.mark.asyncio
    async def test_submitted_branch_time_filter(self):
        paginator = MagicMock(
            after="", before="", has_after=False, has_before=False,
            direction=True, params={},
        )
        fake_iter = _FakeAsyncIterator([], paginator)

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.user.fetch_by_name = AsyncMock(return_value=_make_fake_user())
            mock_client.p.user.pull.submitted.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import fetch_user_profile
            await fetch_user_profile(
                "testuser", content_type="submitted", sort="top", time_filter="year"
            )

        assert paginator.params.get("t") == "year"


# ---------------------------------------------------------------------------
# Tests for search_user_posts
# ---------------------------------------------------------------------------

class TestSearchUserPosts:
    """Test the new search_user_posts tool."""

    @pytest.mark.asyncio
    async def test_delegates_to_submission_search(self):
        fake_sub = _make_fake_submission("Found Post")
        fake_iter = _FakeAsyncIterator([fake_sub])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            result = await search_user_posts("testuser")

        mock_client.p.submission.search.assert_called_once_with(
            "", "author:testuser", 10, sort="new", time="all"
        )
        assert "Posts by u/testuser" in result
        assert "Found Post" in result

    @pytest.mark.asyncio
    async def test_query_appended_to_author_filter(self):
        fake_iter = _FakeAsyncIterator([])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            await search_user_posts("testuser", query="python")

        mock_client.p.submission.search.assert_called_once_with(
            "", "author:testuser python", 10, sort="new", time="all"
        )

    @pytest.mark.asyncio
    async def test_subreddit_passed_through(self):
        fake_iter = _FakeAsyncIterator([])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            result = await search_user_posts("testuser", subreddit="python")

        mock_client.p.submission.search.assert_called_once_with(
            "python", "author:testuser", 10, sort="new", time="all"
        )

    @pytest.mark.asyncio
    async def test_no_results_message(self):
        fake_iter = _FakeAsyncIterator([])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            result = await search_user_posts("testuser")

        assert result == "No posts found for user 'testuser'."

    @pytest.mark.asyncio
    async def test_no_results_with_query(self):
        fake_iter = _FakeAsyncIterator([])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            result = await search_user_posts("testuser", query="nonexistent")

        assert result == "No posts found for user 'testuser' matching 'nonexistent'."

    @pytest.mark.asyncio
    async def test_header_includes_subreddit_when_set(self):
        fake_sub = _make_fake_submission()
        fake_iter = _FakeAsyncIterator([fake_sub])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            result = await search_user_posts("testuser", subreddit="python")

        assert "in r/python" in result

    @pytest.mark.asyncio
    async def test_sort_and_time_filter_passed_through(self):
        fake_iter = _FakeAsyncIterator([])

        with patch("mcp_reddit.reddit_fetcher.client") as mock_client:
            mock_client.p.submission.search.return_value = fake_iter

            from mcp_reddit.reddit_fetcher import search_user_posts
            await search_user_posts(
                "testuser", sort="top", time_filter="month", limit=5
            )

        mock_client.p.submission.search.assert_called_once_with(
            "", "author:testuser", 5, sort="top", time="month"
        )
