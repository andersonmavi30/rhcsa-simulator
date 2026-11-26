"""
Tests for enriched learning-content metadata.
"""

import pytest

from core.content import ContentRegistry


pytestmark = pytest.mark.unit


class TestContentMetadata:
    @pytest.fixture(autouse=True)
    def initialize_registry(self):
        ContentRegistry.initialize()

    def test_topic_contains_study_metadata(self):
        topic = ContentRegistry.get_topic("packages")

        assert topic is not None
        assert topic["study_id"] == "packages"
        assert topic["domain"] == 1
        assert topic["domain_name"]
        assert isinstance(topic["official_objectives"], list)
        assert "official_rhcsa" in topic["content_sources"]
        assert "sander_van_vugt" in topic["content_sources"]

    def test_metadata_lookup_returns_expected_fields(self):
        metadata = ContentRegistry.get_study_metadata("packages")

        assert metadata is not None
        assert metadata["study_id"] == "packages"
        assert metadata["domain"] == 1
        assert metadata["domain_name"]
        assert isinstance(metadata["official_objectives"], list)
        assert isinstance(metadata["content_sources"], list)

    def test_unknown_topic_returns_no_metadata(self):
        assert ContentRegistry.get_study_metadata("does_not_exist") is None
