"""
Tests for helper functions and validation logic in the Reddit MCP server.
These tests cover pure mapping/validation functions that don't require API calls.
"""

import inspect
from unittest.mock import MagicMock

from redditwarp.models.submission_ASYNC import (
    Submission, LinkPost, TextPost, GalleryPost, PollPost, CrosspostSubmission,
)
from redditwarp.models.comment_ASYNC import LooseComment


class TestNormalizeChoice:
    """Test the shared choice-normalization helper."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import _normalize_choice
        self.normalize = _normalize_choice

    def test_valid_choice_is_normalized(self):
        assert self.normalize(" TOP ", {"top", "new"}, "new") == "top"

    def test_invalid_string_falls_back_to_default(self):
        assert self.normalize("invalid", {"top", "new"}, "new") == "new"

    def test_non_string_falls_back_to_default(self):
        assert self.normalize(None, {"top", "new"}, "new") == "new"
        assert self.normalize(123, {"top", "new"}, "new") == "new"


class TestMapCommentSort:
    """Test the _map_comment_sort helper function."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import _map_comment_sort
        self.map_sort = _map_comment_sort

    def test_best_maps_to_confidence(self):
        assert self.map_sort("best") == "confidence"

    def test_best_case_insensitive(self):
        assert self.map_sort("Best") == "confidence"
        assert self.map_sort("BEST") == "confidence"

    def test_top_passes_through(self):
        assert self.map_sort("top") == "top"

    def test_new_passes_through(self):
        assert self.map_sort("new") == "new"

    def test_controversial_passes_through(self):
        assert self.map_sort("controversial") == "controversial"

    def test_old_passes_through(self):
        assert self.map_sort("old") == "old"

    def test_qa_passes_through(self):
        assert self.map_sort("qa") == "qa"

    def test_invalid_falls_back_to_top_for_backward_compatibility(self):
        assert self.map_sort("invalid") == "top"
        assert self.map_sort("") == "top"
        assert self.map_sort("random") == "top"

    def test_non_string_falls_back_to_top(self):
        assert self.map_sort(None) == "top"


class TestGetSubredditSubmissions:
    """Test the _get_subreddit_submissions helper function."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import _get_subreddit_submissions
        self.get_subs = _get_subreddit_submissions

        # Create a mock client with all pull methods
        self.client = MagicMock()
        self.client.p.subreddit.pull.hot = MagicMock(return_value="hot_iter")
        self.client.p.subreddit.pull.new = MagicMock(return_value="new_iter")
        self.client.p.subreddit.pull.top = MagicMock(return_value="top_iter")
        self.client.p.subreddit.pull.rising = MagicMock(return_value="rising_iter")
        self.client.p.subreddit.pull.controversial = MagicMock(return_value="controversial_iter")

    def test_hot_sort(self):
        result = self.get_subs(self.client, "python", 10, "hot", "day")
        assert result == "hot_iter"
        self.client.p.subreddit.pull.hot.assert_called_once_with("python", 10)

    def test_new_sort(self):
        result = self.get_subs(self.client, "python", 5, "new", "day")
        assert result == "new_iter"
        self.client.p.subreddit.pull.new.assert_called_once_with("python", 5)

    def test_top_sort_passes_time_filter(self):
        result = self.get_subs(self.client, "python", 10, "top", "week")
        assert result == "top_iter"
        self.client.p.subreddit.pull.top.assert_called_once_with("python", 10, time="week")

    def test_rising_sort(self):
        result = self.get_subs(self.client, "python", 10, "rising", "day")
        assert result == "rising_iter"
        self.client.p.subreddit.pull.rising.assert_called_once_with("python", 10)

    def test_controversial_sort_passes_time_filter(self):
        result = self.get_subs(self.client, "python", 10, "controversial", "month")
        assert result == "controversial_iter"
        self.client.p.subreddit.pull.controversial.assert_called_once_with("python", 10, time="month")

    def test_invalid_sort_falls_back_to_hot(self):
        result = self.get_subs(self.client, "python", 10, "invalid", "day")
        assert result == "hot_iter"
        self.client.p.subreddit.pull.hot.assert_called_once_with("python", 10)

    def test_sort_case_insensitive(self):
        result = self.get_subs(self.client, "python", 10, "TOP", "week")
        assert result == "top_iter"

    def test_invalid_time_filter_defaults_to_day(self):
        self.get_subs(self.client, "python", 10, "top", "invalid_time")
        self.client.p.subreddit.pull.top.assert_called_once_with("python", 10, time="day")

    def test_non_string_inputs_fall_back_safely(self):
        result = self.get_subs(self.client, "python", 10, None, None)
        assert result == "hot_iter"
        self.client.p.subreddit.pull.hot.assert_called_once_with("python", 10)

    def test_top_with_all_valid_time_filters(self):
        for tf in ["hour", "day", "week", "month", "year", "all"]:
            self.client.p.subreddit.pull.top.reset_mock()
            self.get_subs(self.client, "python", 10, "top", tf)
            self.client.p.subreddit.pull.top.assert_called_once_with("python", 10, time=tf)


class TestGetPostType:
    """Test the _get_post_type helper function."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import _get_post_type
        self.get_type = _get_post_type

    def test_link_post(self):
        mock = MagicMock(spec=LinkPost)
        assert self.get_type(mock) == "link"

    def test_text_post(self):
        mock = MagicMock(spec=TextPost)
        assert self.get_type(mock) == "text"

    def test_gallery_post(self):
        mock = MagicMock(spec=GalleryPost)
        assert self.get_type(mock) == "gallery"

    def test_poll_post(self):
        mock = MagicMock(spec=PollPost)
        assert self.get_type(mock) == "poll"

    def test_crosspost(self):
        mock = MagicMock(spec=CrosspostSubmission)
        assert self.get_type(mock) == "crosspost"

    def test_generic_object_returns_unknown(self):
        assert self.get_type(object()) == "unknown"


class TestGetContent:
    """Test content extraction across supported submission types."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import _get_content
        self.get_content = _get_content

    def test_link_post_uses_outbound_link(self):
        mock = MagicMock(spec=LinkPost)
        mock.link = "https://example.com/article"
        mock.permalink = "https://www.reddit.com/r/test/comments/abc123/example/"
        assert self.get_content(mock) == "https://example.com/article"

    def test_text_post_uses_body(self):
        mock = MagicMock(spec=TextPost)
        mock.body = "hello world"
        assert self.get_content(mock) == "hello world"

    def test_gallery_post_uses_gallery_link(self):
        mock = MagicMock(spec=GalleryPost)
        mock.gallery_link = "https://www.reddit.com/gallery/abc123"
        assert self.get_content(mock) == "https://www.reddit.com/gallery/abc123"

    def test_poll_post_uses_submission_link(self):
        mock = MagicMock(spec=PollPost)
        mock.permalink = "https://www.reddit.com/r/test/comments/abc123/poll/"
        assert self.get_content(mock) == "https://www.reddit.com/r/test/comments/abc123/poll/"

    def test_crosspost_uses_original_link_when_available(self):
        original = MagicMock(spec=Submission)
        original.permalink = "https://www.reddit.com/r/original/comments/orig123/source/"
        mock = MagicMock(spec=CrosspostSubmission)
        mock.original = original
        mock.permalink = "https://www.reddit.com/r/crosspost/comments/cross123/repost/"
        assert self.get_content(mock) == "https://www.reddit.com/r/original/comments/orig123/source/"

    def test_crosspost_falls_back_to_own_link_without_original(self):
        mock = MagicMock(spec=CrosspostSubmission)
        mock.original = None
        mock.permalink = "https://www.reddit.com/r/crosspost/comments/cross123/repost/"
        assert self.get_content(mock) == "https://www.reddit.com/r/crosspost/comments/cross123/repost/"


class TestOverviewTypeBranching:
    """Test that isinstance checks work correctly for all Submission subclasses
    and LooseComment in the user profile overview context."""

    def test_link_post_is_submission(self):
        mock = MagicMock(spec=LinkPost)
        assert isinstance(mock, Submission)

    def test_text_post_is_submission(self):
        mock = MagicMock(spec=TextPost)
        assert isinstance(mock, Submission)

    def test_gallery_post_is_submission(self):
        mock = MagicMock(spec=GalleryPost)
        assert isinstance(mock, Submission)

    def test_poll_post_is_submission(self):
        mock = MagicMock(spec=PollPost)
        assert isinstance(mock, Submission)

    def test_crosspost_is_submission(self):
        mock = MagicMock(spec=CrosspostSubmission)
        assert isinstance(mock, Submission)

    def test_loose_comment_is_not_submission(self):
        mock = MagicMock(spec=LooseComment)
        assert not isinstance(mock, Submission)

    def test_loose_comment_is_loose_comment(self):
        mock = MagicMock(spec=LooseComment)
        assert isinstance(mock, LooseComment)

    def test_submission_is_not_loose_comment(self):
        mock = MagicMock(spec=LinkPost)
        assert not isinstance(mock, LooseComment)


class TestToolDefaults:
    """Test tool signatures for compatibility-sensitive defaults."""

    def test_fetch_reddit_post_content_default_comment_sort_is_top(self):
        from mcp_reddit.reddit_fetcher import fetch_reddit_post_content

        signature = inspect.signature(fetch_reddit_post_content)
        assert signature.parameters["comment_sort"].default == "top"


class TestValidationConstants:
    """Test that validation constants are properly defined."""

    def setup_method(self):
        from mcp_reddit.reddit_fetcher import (
            VALID_SORTS, VALID_TIME_FILTERS, VALID_COMMENT_SORTS,
            VALID_SEARCH_SORTS, VALID_USER_CONTENT_TYPES, VALID_USER_SORTS,
        )
        self.VALID_SORTS = VALID_SORTS
        self.VALID_TIME_FILTERS = VALID_TIME_FILTERS
        self.VALID_COMMENT_SORTS = VALID_COMMENT_SORTS
        self.VALID_SEARCH_SORTS = VALID_SEARCH_SORTS
        self.VALID_USER_CONTENT_TYPES = VALID_USER_CONTENT_TYPES
        self.VALID_USER_SORTS = VALID_USER_SORTS

    def test_valid_sorts(self):
        assert self.VALID_SORTS == {"hot", "new", "top", "rising", "controversial"}

    def test_valid_time_filters(self):
        assert self.VALID_TIME_FILTERS == {"hour", "day", "week", "month", "year", "all"}

    def test_valid_comment_sorts(self):
        assert self.VALID_COMMENT_SORTS == {"best", "top", "new", "controversial", "old", "qa"}

    def test_valid_search_sorts(self):
        assert self.VALID_SEARCH_SORTS == {"relevance", "hot", "top", "new", "comments"}

    def test_valid_user_content_types(self):
        assert self.VALID_USER_CONTENT_TYPES == {"overview", "submitted", "comments"}

    def test_valid_user_sorts(self):
        assert self.VALID_USER_SORTS == {"hot", "new", "top", "controversial"}

    def test_best_not_in_subreddit_sorts(self):
        # 'best' is front-page only, should not be in subreddit sorts
        assert "best" not in self.VALID_SORTS
