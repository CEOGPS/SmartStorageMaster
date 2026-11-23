"""
Test suite for file usage analysis functionality

Tests the UsageAnalyzer, UsageService, and API endpoints
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
import logging

from app.core.usage_analyzer import UsageAnalyzer, UsageMetadata
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)


class TestUsageAnalyzer:
    """Tests for UsageAnalyzer class"""
    
    def test_analyzer_initialization(self):
        """Test analyzer initialization with default parameters"""
        analyzer = UsageAnalyzer()
        assert analyzer.recently_used_days == 30
        assert analyzer.rarely_used_days == 180
        assert analyzer.not_used_days == 180
        assert analyzer.min_priority_size_mb == 100
    
    def test_analyzer_custom_thresholds(self):
        """Test analyzer with custom thresholds"""
        analyzer = UsageAnalyzer(
            recently_used_days=14,
            rarely_used_days=90,
            not_used_days=180,
            min_priority_size_mb=50,
        )
        assert analyzer.recently_used_days == 14
        assert analyzer.rarely_used_days == 90
        assert analyzer.not_used_days == 180
        assert analyzer.min_priority_size_mb == 50
    
    def test_categorize_usage_recently_used(self):
        """Test categorization of recently accessed files"""
        analyzer = UsageAnalyzer(recently_used_days=30)
        category = analyzer._categorize_usage(days_since_access=15)
        assert category == "RECENTLY_USED"
    
    def test_categorize_usage_rarely_used(self):
        """Test categorization of rarely used files"""
        analyzer = UsageAnalyzer(rarely_used_days=180)
        category = analyzer._categorize_usage(days_since_access=90)
        assert category == "RARELY_USED"
    
    def test_categorize_usage_not_used(self):
        """Test categorization of unused files"""
        analyzer = UsageAnalyzer(not_used_days=180)
        category = analyzer._categorize_usage(days_since_access=365)
        assert category == "NOT_USED"
    
    def test_priority_calculation_not_used(self):
        """Test priority score for NOT_USED files"""
        analyzer = UsageAnalyzer()
        
        # Small unused file
        priority = analyzer._calculate_priority("NOT_USED", size=1024, days_since=200)
        assert 0.8 < priority < 1.0
        
        # Large unused file
        priority_large = analyzer._calculate_priority(
            "NOT_USED",
            size=200 * 1024 * 1024,
            days_since=200
        )
        assert priority_large > priority
    
    def test_priority_calculation_rarely_used(self):
        """Test priority score for RARELY_USED files"""
        analyzer = UsageAnalyzer()
        priority = analyzer._calculate_priority("RARELY_USED", size=1024, days_since=90)
        assert 0.4 < priority < 0.6
    
    def test_priority_calculation_recently_used(self):
        """Test priority score for RECENTLY_USED files"""
        analyzer = UsageAnalyzer()
        priority = analyzer._calculate_priority("RECENTLY_USED", size=1024, days_since=10)
        assert 0.0 < priority < 0.2
    
    def test_priority_large_file_bonus(self):
        """Test that large files get priority bonus"""
        analyzer = UsageAnalyzer(min_priority_size_mb=100)
        
        small_file_priority = analyzer._calculate_priority(
            "RARELY_USED",
            size=10 * 1024 * 1024,  # 10 MB
            days_since=90
        )
        
        large_file_priority = analyzer._calculate_priority(
            "RARELY_USED",
            size=200 * 1024 * 1024,  # 200 MB
            days_since=90
        )
        
        assert large_file_priority > small_file_priority
    
    def test_analyze_file_with_temp_file(self):
        """Test analyzing a temporary file"""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")
            
            analyzer = UsageAnalyzer()
            metadata = analyzer.analyze_file(test_file)
            
            assert metadata is not None
            assert metadata.path == test_file
            assert metadata.size == len("test content")
            assert metadata.usage_category in ["RECENTLY_USED", "RARELY_USED", "NOT_USED"]
            assert 0.0 <= metadata.usage_priority <= 1.0
    
    def test_batch_analyze(self):
        """Test batch analysis of multiple files"""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            test_files = []
            for i in range(5):
                f = Path(tmpdir) / f"test_{i}.txt"
                f.write_text(f"content {i}")
                test_files.append(f)
            
            analyzer = UsageAnalyzer()
            results = analyzer.batch_analyze(test_files)
            
            # Should have 5 files categorized
            total_files = (
                len(results["RECENTLY_USED"]) +
                len(results["RARELY_USED"]) +
                len(results["NOT_USED"])
            )
            assert total_files == 5


class TestUsageCategories:
    """Integration tests for usage categorization"""
    
    def test_category_threshold_boundaries(self):
        """Test that threshold boundaries are correctly applied"""
        analyzer = UsageAnalyzer(
            recently_used_days=30,
            rarely_used_days=90,
            not_used_days=180,
        )
        
        # Day 30 should be RECENTLY_USED
        assert analyzer._categorize_usage(30) == "RECENTLY_USED"
        # Day 31 should be RARELY_USED
        assert analyzer._categorize_usage(31) == "RARELY_USED"
        # Day 90 should be RARELY_USED
        assert analyzer._categorize_usage(90) == "RARELY_USED"
        # Day 181 should be NOT_USED
        assert analyzer._categorize_usage(181) == "NOT_USED"
    
    def test_summary_statistics(self):
        """Test summary statistics calculation"""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            test_files = []
            for i in range(10):
                f = Path(tmpdir) / f"test_{i}.txt"
                f.write_text("x" * 1024)  # 1 KB each
                test_files.append(f)
            
            analyzer = UsageAnalyzer()
            metadata_list = []
            for f in test_files:
                m = analyzer.analyze_file(f)
                if m:
                    metadata_list.append(m)
            
            stats = analyzer.get_summary_statistics(metadata_list)
            
            assert stats["total_files"] == len(metadata_list)
            assert stats["total_size_mb"] > 0
            assert "categories" in stats


class TestPriorityCalculation:
    """Tests for cleanup priority calculation"""
    
    def test_priority_range(self):
        """Test that priority is always between 0.0 and 1.0"""
        analyzer = UsageAnalyzer()
        
        # Test various combinations
        for category in ["RECENTLY_USED", "RARELY_USED", "NOT_USED"]:
            for size in [1024, 100 * 1024 * 1024, 1024 * 1024 * 1024]:
                for days in [1, 30, 90, 180, 365]:
                    priority = analyzer._calculate_priority(category, size, days)
                    assert 0.0 <= priority <= 1.0
    
    def test_priority_ordering(self):
        """Test that priority ordering is consistent with expectations"""
        analyzer = UsageAnalyzer()
        
        # NOT_USED should have highest priority
        not_used = analyzer._calculate_priority("NOT_USED", 1024, 365)
        rarely_used = analyzer._calculate_priority("RARELY_USED", 1024, 90)
        recently_used = analyzer._calculate_priority("RECENTLY_USED", 1024, 15)
        
        assert not_used > rarely_used > recently_used
    
    def test_age_bonus_accumulation(self):
        """Test that very old unused files get higher priority"""
        analyzer = UsageAnalyzer()
        
        # Newer NOT_USED file
        newer_priority = analyzer._calculate_priority("NOT_USED", 1024, 200)
        
        # Very old NOT_USED file
        older_priority = analyzer._calculate_priority("NOT_USED", 1024, 500)
        
        assert older_priority >= newer_priority


class TestCleanupCandidates:
    """Tests for cleanup candidate selection"""
    
    def test_get_cleanup_candidates_priority_filter(self):
        """Test filtering by minimum priority"""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            test_files = []
            for i in range(10):
                f = Path(tmpdir) / f"test_{i}.txt"
                f.write_text("content")
                test_files.append(f)
            
            analyzer = UsageAnalyzer()
            metadata_list = []
            for f in test_files:
                m = analyzer.analyze_file(f)
                if m:
                    metadata_list.append(m)
            
            # Get candidates with high priority filter
            candidates = analyzer.get_cleanup_candidates(
                metadata_list,
                min_priority=0.8
            )
            
            # Should have fewer candidates than total
            assert len(candidates) <= len(metadata_list)
            
            # All candidates should meet priority threshold
            for candidate in candidates:
                assert candidate.usage_priority >= 0.8
    
    def test_cleanup_candidates_sorted_by_priority(self):
        """Test that cleanup candidates are sorted correctly"""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            test_files = []
            for i in range(5):
                f = Path(tmpdir) / f"test_{i}.txt"
                f.write_text("x" * (1024 * 100 * i))  # Increasing sizes
                test_files.append(f)
            
            analyzer = UsageAnalyzer()
            metadata_list = []
            for f in test_files:
                m = analyzer.analyze_file(f)
                if m:
                    metadata_list.append(m)
            
            candidates = analyzer.get_cleanup_candidates(
                metadata_list,
                min_priority=0.0
            )
            
            # Should be sorted by priority (descending)
            for i in range(len(candidates) - 1):
                assert candidates[i].usage_priority >= candidates[i + 1].usage_priority


class TestAPIEndpoints:
    """Tests for REST API endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_summary_endpoint(self):
        """Test GET /api/usage/summary endpoint"""
        # This would require setting up FastAPI test client
        # Placeholder for integration testing
        pass
    
    @pytest.mark.asyncio
    async def test_get_files_by_category_endpoint(self):
        """Test GET /api/usage/files endpoint"""
        # This would require setting up FastAPI test client
        # Placeholder for integration testing
        pass
    
    @pytest.mark.asyncio
    async def test_get_recommendations_endpoint(self):
        """Test GET /api/usage/recommendations endpoint"""
        # This would require setting up FastAPI test client
        # Placeholder for integration testing
        pass


# Test runner
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
