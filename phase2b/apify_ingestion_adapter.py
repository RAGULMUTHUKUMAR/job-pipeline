#!/usr/bin/env python3
"""
Phase 7: Apify Job Ingestion / Input Adapter

Connects Apify MCP (curious_coder/linkedin-jobs-scraper) to the pipeline's
raw_records.json format. Fetches fresh job listings, transforms to canonical
raw format, validates required fields, and stores test results separately
from production baseline.

Hard constraints:
- NO modification of scoring logic
- NO application automation
- NO changes to frozen files
- NO overwrite of verified outputs
- Max 5 test jobs per run
- Preserve source metadata
- Validate required fields for pipeline.py compatibility
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class ApifyIngestionAdapter:
    """Transforms Apify LinkedIn Jobs Scraper output to pipeline raw format."""

    # Required fields in the TRANSFORMED record (pipeline raw format)
    # These match the original Apify field names (camelCase) + computed fields
    REQUIRED_FIELDS = [
        "job_id",  # computed
        "title",  # original Apify
        "companyName",  # original Apify
        "location",  # original Apify
        "posted_date",  # computed (normalized from postedAt)
        "descriptionText",  # original Apify
        "employmentType",  # original Apify
        "jobFunction",  # original Apify
        "industries",  # original Apify
        "inputUrl",  # original Apify
        "link",  # original Apify
    ]

    # Fields that are nice to have but not required
    OPTIONAL_FIELDS = [
        "trackingId",
        "refId",
        "companyLinkedinUrl",
        "companyLogo",
        "benefits",
        "descriptionHtml",
        "applicantsCount",
        "applyUrl",
        "salary",
        "seniorityLevel",
        "jobPosterName",
        "jobPosterTitle",
        "jobPosterPhoto",
        "jobPosterProfileUrl",
        "companyAddress",
        "companyWebsite",
        "companySlogan",
        "companyDescription",
        "companyEmployeesCount",
    ]

    def __init__(
        self,
        max_jobs: int = 5,
        output_dir: str = "output",
        test_prefix: str = "test_ingestion_",
    ):
        self.max_jobs = max_jobs
        self.output_dir = output_dir
        self.test_prefix = test_prefix
        os.makedirs(output_dir, exist_ok=True)

    def _generate_job_id(self, item: Dict[str, Any]) -> str:
        """Generate deterministic job_id from Apify item."""
        # Use the LinkedIn job ID as the primary identifier
        linkedin_id = item.get("id", "")
        if linkedin_id:
            return f"linkedin_{linkedin_id}"

        # Fallback: hash of link + title + company
        import hashlib

        key = f"{item.get('link', '')}{item.get('title', '')}{item.get('companyName', '')}"
        return f"linkedin_{hashlib.md5(key.encode()).hexdigest()[:12]}"

    def _extract_location_parts(self, location: str) -> Dict[str, Optional[str]]:
        """Parse location string into components."""
        if not location:
            return {"city": None, "state": None, "country": "IN"}

        parts = [p.strip() for p in location.split(",")]

        # Handle special case: "India" alone means country=IN, city=None
        if len(parts) == 1 and parts[0].lower() == "india":
            return {"city": None, "state": None, "country": "IN"}

        # Handle "State, India" case (no city)
        if len(parts) == 2 and parts[1].lower() == "india":
            return {"city": None, "state": parts[0], "country": "IN"}

        result = {"city": None, "state": None, "country": "IN"}

        if len(parts) >= 1:
            result["city"] = parts[0]
        if len(parts) >= 2:
            # Second part is state unless it's "India"
            second = parts[1]
            if second.lower() != "india":
                result["state"] = second
        if len(parts) >= 3:
            # Third part is country (map "India" to IN)
            third = parts[2]
            result["country"] = "IN" if third.lower() == "india" else third

        return result

    def _extract_skills_from_description(self, description: str) -> List[str]:
        """Extract potential skills from job description text."""
        if not description:
            return []

        # Common tech skills to look for
        skill_keywords = [
            "javascript",
            "typescript",
            "react",
            "node.js",
            "nodejs",
            "express",
            "next.js",
            "nextjs",
            "vue",
            "angular",
            "html",
            "css",
            "sass",
            "webpack",
            "vite",
            "babel",
            "jest",
            "cypress",
            "testing",
            "git",
            "github",
            "gitlab",
            "ci/cd",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "gcp",
            "cloud",
            "sql",
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "graphql",
            "rest",
            "api",
            "microservices",
            "python",
            "java",
            "go",
            "rust",
            "c++",
            "c#",
            ".net",
            "spring",
            "django",
            "flask",
            "fastapi",
            "nestjs",
            "redux",
            "mobx",
            "context",
            "hooks",
            "tailwind",
            "bootstrap",
            "material-ui",
            "chakra",
            "styled-components",
            "emotion",
            "webpack",
            "rollup",
            "parcel",
            "esbuild",
            "swc",
            "jest",
            "vitest",
            "mocha",
            "chai",
            "sinon",
            "enzyme",
            "react-testing-library",
            "playwright",
            "puppeteer",
            "typescript",
            "eslint",
            "prettier",
            "husky",
            "lint-staged",
            "n8n",
            "cursor",
            "claude",
            "ai",
            "llm",
            "prompt",
        ]

        found_skills = []
        desc_lower = description.lower()
        for skill in skill_keywords:
            if skill.lower() in desc_lower:
                # Normalize common variations
                if skill in ["node.js", "nodejs"]:
                    found_skills.append("Node.js")
                elif skill in ["next.js", "nextjs"]:
                    found_skills.append("Next.js")
                elif skill == "ci/cd":
                    found_skills.append("CI/CD")
                elif skill == "rest":
                    found_skills.append("REST API")
                elif skill == "graphql":
                    found_skills.append("GraphQL")
                elif skill == "sql":
                    found_skills.append("SQL")
                else:
                    found_skills.append(
                        skill.title() if skill != skill.upper() else skill
                    )

        # Deduplicate while preserving order
        seen = set()
        unique_skills = []
        for skill in found_skills:
            if skill.lower() not in seen:
                seen.add(skill.lower())
                unique_skills.append(skill)

        return unique_skills[:20]  # Limit to top 20

    def _extract_experience_years(self, description: str) -> Dict[str, Optional[int]]:
        """Extract experience requirements from description."""
        import re

        min_years = None
        max_years = None

        # Look for patterns like "X years", "X+ years", "X-Y years"
        patterns = [
            r"(\d+)\+?\s*years?\s*(?:of\s*)?experience",
            r"(\d+)\s*-\s*(\d+)\s*years?\s*(?:of\s*)?experience",
            r"(\d+)\s*-\s*(\d+)\s*years?\s*(?:in|of|experience|development|work)",  # "4-7 years in software"
            r"minimum\s+(\d+)\s*years?",
            r"at least\s+(\d+)\s*years?",
            r"(\d+)\s*year\s*experience",
            r"experience\s*:\s*(\d+)\+?\s*years?",  # "Experience: 5+ years"
            r"(\d+)\+?\s*years?\s*(?:experience|exp\.)",  # "5 years experience"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, description.lower())
            if matches:
                if isinstance(matches[0], tuple):
                    # Range pattern
                    min_years = int(matches[0][0])
                    max_years = int(matches[0][1])
                else:
                    # Single number
                    min_years = int(matches[0])
                break

        return {"min": min_years, "max": max_years}

    def _parse_posted_date(self, posted_at: str) -> str:
        """Normalize posted date to ISO format."""
        if not posted_at:
            return datetime.now().date().isoformat()

        # Try to parse various formats
        formats = [
            "%Y-%m-%d",
            "%b %d, %Y",
            "%d %b %Y",
            "%B %d, %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(posted_at.strip(), fmt).date().isoformat()
            except ValueError:
                continue

        # If all fail, return today
        return datetime.now().date().isoformat()

    def _determine_workplace_type(self, description: str, location: str) -> str:
        """Infer workplace type from description and location."""
        if not description:
            return "UNKNOWN"

        desc_lower = description.lower()

        # Check for remote indicators
        remote_keywords = ["remote", "work from home", "wfh", "distributed", "anywhere"]
        if any(kw in desc_lower for kw in remote_keywords):
            return "REMOTE"

        # Check for hybrid indicators
        hybrid_keywords = ["hybrid", "flexible", "office days", "on-site required"]
        if any(kw in desc_lower for kw in hybrid_keywords):
            return "HYBRID"

        # Default to on-site for Indian locations
        return "ON_SITE"

    def transform_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single Apify item to pipeline raw format.

        Preserves ALL original Apify fields (matching raw_records.json schema)
        and adds computed metadata fields.
        """
        # Generate job_id
        job_id = self._generate_job_id(item)

        # Extract location parts
        location_parts = self._extract_location_parts(item.get("location", ""))

        # Extract skills from description
        description_text = item.get("descriptionText", "") or item.get(
            "descriptionHtml", ""
        )
        skills = self._extract_skills_from_description(description_text)

        # Extract experience requirements
        exp = self._extract_experience_years(description_text)

        # Determine workplace type
        workplace_type = self._determine_workplace_type(
            description_text, item.get("location", "")
        )

        # Parse posted date
        posted_date = self._parse_posted_date(item.get("postedAt", ""))

        # Build transformed record - START with all original Apify fields
        transformed = dict(item)  # Copy all original fields

        # Add computed metadata fields
        transformed.update(
            {
                "job_id": job_id,
                "source": "linkedin",
                "source_job_id": item.get("id", ""),
                "city": location_parts["city"],
                "state": location_parts["state"],
                "country": location_parts["country"],
                "workplace_type": workplace_type,
                "posted_date": posted_date,
                "extracted_skills": skills,
                "required_experience_min": exp["min"],
                "required_experience_max": exp["max"],
                "ingestion_timestamp": datetime.now().isoformat(),
                "ingestion_source": "apify_linkedin_jobs_scraper",
            }
        )

        return transformed

    def validate_record(self, record: Dict[str, Any]) -> List[str]:
        """Validate a transformed record. Returns list of errors (empty if valid)."""
        errors = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            value = record.get(field)
            if value is None or value == "":
                errors.append(f"Missing required field: {field}")

        # Validate job_id format
        job_id = record.get("job_id", "")
        if not job_id.startswith("linkedin_"):
            errors.append(f"Invalid job_id format: {job_id}")

        # Validate URL format for link
        link = record.get("link", "")
        if link:
            try:
                result = urlparse(link)
                if not all([result.scheme, result.netloc]):
                    errors.append(f"Invalid link URL: {link}")
            except Exception:
                errors.append(f"Invalid link URL format: {link}")

        # Validate posted_date format
        posted_date = record.get("posted_date", "")
        try:
            datetime.fromisoformat(posted_date)
        except ValueError:
            errors.append(f"Invalid posted_date format: {posted_date}")

        # Validate country
        country = record.get("country", "")
        if country and len(country) != 2:
            errors.append(f"Country should be 2-letter code: {country}")

        return errors

    def run(self, dataset_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run the ingestion adapter on a list of Apify dataset items."""
        print(f"Starting Apify ingestion adapter...")
        print(f"Input items: {len(dataset_items)}")
        print(f"Max jobs to process: {self.max_jobs}")

        # Limit to max_jobs
        items_to_process = dataset_items[: self.max_jobs]
        print(f"Processing {len(items_to_process)} items...")

        # Transform each item
        transformed_records = []
        validation_errors = []

        for i, item in enumerate(items_to_process):
            print(
                f"  Processing item {i+1}/{len(items_to_process)}: {item.get('title', 'Unknown')} at {item.get('companyName', 'Unknown')}"
            )
            transformed = self.transform_item(item)
            errors = self.validate_record(transformed)

            if errors:
                validation_errors.append(
                    {
                        "index": i,
                        "source_id": item.get("id", "unknown"),
                        "errors": errors,
                    }
                )
                print(f"    WARNING: Validation errors: {errors}")
            else:
                print(f"    OK: {transformed['job_id']}")

            transformed_records.append(transformed)

        # Create output structure matching raw_records.json format
        output = {
            "datasetId": f"apify_ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "items": transformed_records,
            "ingestion_metadata": {
                "timestamp": datetime.now().isoformat(),
                "source_actor": "curious_coder/linkedin-jobs-scraper",
                "total_input_items": len(dataset_items),
                "processed_items": len(items_to_process),
                "max_jobs_limit": self.max_jobs,
                "validation_errors_count": len(validation_errors),
                "valid_records": len(transformed_records) - len(validation_errors),
            },
            "validation_errors": validation_errors,
        }

        # Save to test output file (NOT overwriting production raw_records.json)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_filename = f"{self.test_prefix}{timestamp}.json"
        test_path = os.path.join(self.output_dir, test_filename)

        with open(test_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nTest ingestion saved to: {test_path}")
        print(f"Valid records: {output['ingestion_metadata']['valid_records']}")
        print(
            f"Validation errors: {output['ingestion_metadata']['validation_errors_count']}"
        )

        return {
            "test_output_path": test_path,
            "records": transformed_records,
            "errors": validation_errors,
            "metadata": output["ingestion_metadata"],
        }

    def run_self_test(self, dataset_items: List[Dict[str, Any]]) -> bool:
        """Run self-test to verify deterministic transformation."""
        print("\nRunning self-test: deterministic transformation...")

        # Run transformation twice
        result1 = self.run(dataset_items)
        result2 = self.run(dataset_items)

        # Compare job_ids (should be deterministic)
        ids1 = [r["job_id"] for r in result1["records"]]
        ids2 = [r["job_id"] for r in result2["records"]]

        if ids1 != ids2:
            print("FAIL: Job IDs not deterministic across runs")
            print(f"  Run 1: {ids1}")
            print(f"  Run 2: {ids2}")
            return False

        # Compare full records (excluding timestamps)
        for r1, r2 in zip(result1["records"], result2["records"]):
            # Create copies without timestamps for comparison
            c1 = {k: v for k, v in r1.items() if k != "ingestion_timestamp"}
            c2 = {k: v for k, v in r2.items() if k != "ingestion_timestamp"}
            if c1 != c2:
                print("FAIL: Records not identical across runs (excluding timestamps)")
                return False

        print("PASS: Transformation is deterministic")
        return True


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Apify Job Ingestion Adapter")
    parser.add_argument(
        "--dataset-id", required=True, help="Apify dataset ID to fetch items from"
    )
    parser.add_argument(
        "--max-jobs", type=int, default=5, help="Maximum jobs to process (default: 5)"
    )
    parser.add_argument(
        "--output-dir", default="output", help="Output directory (default: output)"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test for deterministic transformation",
    )
    args = parser.parse_args()

    # Note: In actual usage, you'd fetch from Apify API here
    # For this script, we expect the dataset items to be passed via stdin or file
    # Since we're running in the context where we already have the data, we'll read from stdin

    print("Reading dataset items from stdin...")
    try:
        input_data = json.load(sys.stdin)
        if isinstance(input_data, dict) and "items" in input_data:
            dataset_items = input_data["items"]
        elif isinstance(input_data, list):
            dataset_items = input_data
        else:
            print("ERROR: Expected JSON with 'items' array or direct array")
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON input: {e}")
        sys.exit(1)

    print(f"Loaded {len(dataset_items)} items from stdin")

    adapter = ApifyIngestionAdapter(
        max_jobs=args.max_jobs,
        output_dir=args.output_dir,
    )

    if args.self_test:
        success = adapter.run_self_test(dataset_items)
        sys.exit(0 if success else 1)
    else:
        result = adapter.run(dataset_items)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
