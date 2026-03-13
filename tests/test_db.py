"""Unit tests for the database layer."""

from scholar_tracker.models.database import (
    get_paper_by_title,
    get_total_citations,
    get_tracked_papers,
    update_paper_citations,
)


class TestUpdatePaperCitations:
    """Tests for update_paper_citations()."""

    def test_new_paper_is_inserted(self, fresh_db):
        """First time tracking a paper should insert it."""
        has_changed, delta = update_paper_citations("Test Paper", 42)

        assert has_changed is True
        assert delta == 0  # Initial seed has delta=0

        paper = get_paper_by_title("Test Paper")
        assert paper is not None
        assert paper["title"] == "Test Paper"
        assert paper["current_citations"] == 42

    def test_citation_increase_detected(self, fresh_db):
        """Increasing citations should be detected and recorded."""
        update_paper_citations("Test Paper", 100)

        has_changed, delta = update_paper_citations("Test Paper", 105)

        assert has_changed is True
        assert delta == 5

    def test_no_change_when_citations_same(self, fresh_db):
        """Same citation count should return no change."""
        update_paper_citations("Test Paper", 100)

        has_changed, delta = update_paper_citations("Test Paper", 100)

        assert has_changed is False
        assert delta == 0

    def test_decrease_ignored(self, fresh_db):
        """Citation decreases (data fluctuation) should be ignored."""
        update_paper_citations("Test Paper", 100)

        has_changed, delta = update_paper_citations("Test Paper", 98)

        assert has_changed is False
        assert delta == 0


class TestGetTotalCitations:
    """Tests for get_total_citations()."""

    def test_empty_db_returns_zero(self, fresh_db):
        assert get_total_citations() == 0

    def test_sums_all_papers(self, fresh_db):
        update_paper_citations("Paper A", 50)
        update_paper_citations("Paper B", 30)

        assert get_total_citations() == 80

    def test_tracks_updates(self, fresh_db):
        update_paper_citations("Paper A", 50)
        update_paper_citations("Paper A", 55)

        assert get_total_citations() == 55


class TestGetTrackedPapers:
    """Tests for get_tracked_papers()."""

    def test_empty_db(self, fresh_db):
        assert get_tracked_papers() == []

    def test_returns_all_papers(self, fresh_db):
        update_paper_citations("Paper A", 10)
        update_paper_citations("Paper B", 20)

        papers = get_tracked_papers()
        assert len(papers) == 2
        titles = {p["title"] for p in papers}
        assert titles == {"Paper A", "Paper B"}


class TestGetPaperByTitle:
    """Tests for get_paper_by_title()."""

    def test_not_found_returns_none(self, fresh_db):
        assert get_paper_by_title("Nonexistent") is None

    def test_finds_existing_paper(self, fresh_db):
        update_paper_citations("My Paper", 42)

        paper = get_paper_by_title("My Paper")
        assert paper is not None
        assert paper["current_citations"] == 42
