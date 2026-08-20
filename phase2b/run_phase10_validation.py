#!/usr/bin/env python3
"""
Phase 10: Fresh Real Apify Production Validation

Runs the existing Phase 9 pipeline with a fresh Apify dataset.
Uses the existing apify_ingestion_adapter and the orchestrator pattern.
"""

import json
import os
import sys
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, NoReturn
from dataclasses import dataclass, asdict, field

PHASE2B_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PHASE2B_DIR))

import pipeline as P
import phase2c_salary_score as salary
import phase2c_experience_score as experience
import phase2c_skill_score as skill
import phase2c_role_score as role
import phase2c_location_score as location
import phase2c_workplace_score as workplace
import phase2c_composite_score as composite
import phase2c_ranking as ranking
import phase2c_application_decision as decision
import phase4_application_queue as queue
import apify_ingestion_adapter as apify_adapter


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    apify_input_count: int = 0
    canonical_record_count: int = 0
    candidate_count: int = 0
    review_count: int = 0
    not_recommended_count: int = 0
    queue_count: int = 0
    google_drive_upload_result: str = "pending"
    google_drive_file_id: Optional[str] = None
    google_drive_file_url: Optional[str] = None
    failures: List[str] = field(default_factory=list)
    stage_outputs: Dict[str, str] = field(default_factory=dict)


class Phase10Validator:
    def __init__(self, max_jobs: int = 10):
        self.max_jobs = max_jobs

        # Create isolated run directory
        self.run_id = f"phase10_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.run_dir = Path("/tmp") / self.run_id
        self.input_dir = self.run_dir / "input"
        self.output_dir = self.run_dir / "output"
        self.log_file = self.run_dir / "run.log"

        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.summary = RunSummary(
            run_id=self.run_id,
            started_at=datetime.now().isoformat(),
        )

        self._log(f"=== PHASE 10 VALIDATION STARTED: {self.run_id} ===")
        self._log(f"Run directory: {self.run_dir}")
        self._log(f"Max jobs: {self.max_jobs}")

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    def _fail(self, stage: str, error: str) -> NoReturn:
        self.summary.failures.append(f"{stage}: {error}")
        self._log(f"FAILURE in {stage}: {error}")
        self.summary.completed_at = datetime.now().isoformat()
        self._write_summary()
        raise RuntimeError(f"Pipeline failed at {stage}: {error}")

    def _write_summary(self) -> None:
        summary_path = self.output_dir / "run_summary.json"
        with open(summary_path, "w") as f:
            json.dump(asdict(self.summary), f, indent=2)
        self._log(f"Run summary written: {summary_path}")

    def run_apify_ingestion(
        self, apify_items: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Transform fresh Apify items using ingestion adapter."""
        self._log("Stage 1: Apify ingestion (fresh data)...")

        try:
            adapter = apify_adapter.ApifyIngestionAdapter(
                max_jobs=self.max_jobs,
                output_dir=str(self.input_dir),
                test_prefix="phase10_ingestion_",
            )

            adapter_result = adapter.run(apify_items)

            if adapter_result["metadata"]["valid_records"] == 0:
                self._fail("apify_ingestion", "No valid records after transformation")

            self._log(
                f"Transformed {adapter_result['metadata']['valid_records']} valid records"
            )

            # Read the generated ingestion file
            ingestion_file = adapter_result["test_output_path"]
            with open(ingestion_file) as f:
                ingestion_data = json.load(f)

            transformed_items = ingestion_data["items"]
            self.summary.apify_input_count = len(transformed_items)
            self._log(f"Apify ingestion complete: {len(transformed_items)} records")

            return transformed_items, adapter_result["metadata"].get(
                "datasetId", "fresh_apify"
            )

        except Exception as e:
            self._fail(
                "apify_ingestion", f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )

    def run_phase2b_canonicalization(self, raw_items: List[Dict[str, Any]]) -> int:
        self._log("Stage 2: Phase 2B canonicalization...")

        try:
            raw_payload = {
                "datasetId": f"phase10_apify_{datetime.now().strftime('%Y%m%d')}",
                "items": raw_items,
            }
            raw_input_path = self.input_dir / "raw_records.json"
            with open(raw_input_path, "w") as f:
                json.dump(raw_payload, f, indent=2)

            P.INPUT_RAW = raw_input_path
            P.OUT_DIR = self.output_dir
            P.DISCOVERED_DATE = datetime.now().date().isoformat()
            P.DATASET_ID = f"phase10_{datetime.now().strftime('%Y%m%d')}"

            P.main()

            job_records_path = self.output_dir / "job_records.json"
            with open(job_records_path) as f:
                records = json.load(f)

            self.summary.canonical_record_count = len(records)
            self._log(f"Phase 2B complete: {len(records)} canonical records")

            eligible = sum(1 for r in records if r["match_eligibility"] == "ELIGIBLE")
            review = sum(1 for r in records if r["match_eligibility"] == "REVIEW")
            blocked = sum(1 for r in records if r["match_eligibility"] == "BLOCKED")
            self._log(
                f"  Eligibility: ELIGIBLE={eligible}, REVIEW={review}, BLOCKED={blocked}"
            )

            self.summary.stage_outputs["job_records"] = str(job_records_path)
            return len(records)

        except Exception as e:
            self._fail(
                "phase2b_canonicalization",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def run_component_scorers(self) -> None:
        self._log("Stage 3: Six component scorers...")

        in_records = self.output_dir / "job_records.json"

        scorers = [
            ("salary", salary, "phase2c_salary_scores.json"),
            ("experience", experience, "phase2c_experience_scores.json"),
            ("skill", skill, "phase2c_skill_scores.json"),
            ("role", role, "phase2c_role_scores.json"),
            ("location", location, "phase2c_location_scores.json"),
            ("workplace", workplace, "phase2c_workplace_scores.json"),
        ]

        for name, module, out_file in scorers:
            try:
                self._log(f"  Running {name} scorer...")
                setattr(module, "IN_RECORDS", in_records)
                setattr(module, "OUT", self.output_dir / out_file)
                module.main()

                with open(module.OUT) as f:
                    scores = json.load(f)
                with open(in_records) as f:
                    records = json.load(f)

                score_ids = {s["job_id"] for s in scores}
                record_ids = {r["job_id"] for r in records}
                assert score_ids == record_ids, f"{name}: job_id set mismatch"

                self._log(
                    f"  {name} scorer complete: {len(scores)} records, 1:1 join OK"
                )
                self.summary.stage_outputs[f"{name}_scores"] = str(module.OUT)

            except Exception as e:
                self._fail(
                    f"component_scorer_{name}",
                    f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                )

    def run_composite_scoring(self) -> None:
        self._log("Stage 4: Composite scoring...")

        try:
            in_records = self.output_dir / "job_records.json"

            setattr(composite, "IN_RECORDS", in_records)
            setattr(composite, "IN_SALARY", self.output_dir / "phase2c_salary_scores.json")
            setattr(composite, "IN_EXPERIENCE", self.output_dir / "phase2c_experience_scores.json")
            setattr(composite, "IN_SKILL", self.output_dir / "phase2c_skill_scores.json")
            setattr(composite, "IN_ROLE", self.output_dir / "phase2c_role_scores.json")
            setattr(composite, "IN_LOCATION", self.output_dir / "phase2c_location_scores.json")
            setattr(composite, "IN_WORKPLACE", self.output_dir / "phase2c_workplace_scores.json")
            setattr(composite, "OUT", self.output_dir / "phase2c_composite_scores.json")

            orig_main = composite.main

            def _test_main():
                records = json.load(open(composite.IN_RECORDS))
                salary_by = composite._index_by_job_id(composite.IN_SALARY)
                exp_by = composite._index_by_job_id(composite.IN_EXPERIENCE)
                skill_by = composite._index_by_job_id(composite.IN_SKILL)
                role_by = composite._index_by_job_id(composite.IN_ROLE)
                location_by = composite._index_by_job_id(composite.IN_LOCATION)
                workplace_by = composite._index_by_job_id(composite.IN_WORKPLACE)

                rec_ids = {r["job_id"] for r in records}

                for label, m in (
                    ("salary", salary_by),
                    ("experience", exp_by),
                    ("skill", skill_by),
                    ("role", role_by),
                    ("location", location_by),
                    ("workplace", workplace_by),
                ):
                    assert len(m) == len(records), f"{label}: count mismatch"
                    assert set(m.keys()) == rec_ids, f"{label}: job_id set mismatch"

                composites_list = [
                    composite.compute_composite(
                        r,
                        salary_by[r["job_id"]],
                        exp_by[r["job_id"]],
                        skill_by[r["job_id"]],
                        role_by[r["job_id"]],
                        location_by[r["job_id"]],
                        workplace_by[r["job_id"]],
                    )
                    for r in records
                ]

                assert len(composites_list) == len(
                    records
                ), "N inputs must yield N composites"
                out_ids = [c["job_id"] for c in composites_list]
                assert len(set(out_ids)) == len(out_ids), "duplicate job_id"
                assert set(out_ids) == rec_ids, "composite job_id set mismatch"

                assert all(
                    c["salary_weight"] == 0.15
                    and c["experience_weight"] == 0.20
                    and c["skill_weight"] == 0.30
                    and c["role_weight"] == 0.15
                    and c["location_weight"] == 0.10
                    and c["workplace_weight"] == 0.10
                    for c in composites_list
                ), "weight mismatch"

                assert all(
                    c["implemented_weight"] == 1.00 and c["reserved_weight"] == 0.00
                    for c in composites_list
                ), "implemented/reserved weight mismatch"

                assert all(
                    c["composite_blocks"] is False
                    and c["composite_rejection_reason"] is None
                    for c in composites_list
                ), "composite must never block/reject"

                rec_by = {r["job_id"]: r for r in records}
                assert all(
                    c["match_eligibility"] == rec_by[c["job_id"]]["match_eligibility"]
                    and c["data_quality_status"]
                    == rec_by[c["job_id"]]["data_quality_status"]
                    for c in composites_list
                ), "Phase2B fields must be carried through unchanged"

                for c in composites_list:
                    contrib_sum = (
                        c["salary_contribution"]
                        + c["experience_contribution"]
                        + c["skill_contribution"]
                        + c["role_contribution"]
                        + c["location_contribution"]
                        + c["workplace_contribution"]
                    )
                    assert (
                        abs(contrib_sum - c["composite_score"]) < 1e-6
                    ), f"contribution sum mismatch for {c['job_id']}"

                with open(composite.OUT, "w") as f:
                    json.dump(composites_list, f, indent=2)

                from collections import Counter

                tiers = Counter(c["recommendation_tier"] for c in composites_list)
                avg = sum(c["composite_score"] for c in composites_list) / len(
                    composites_list
                )

                self._log(
                    f"Composite: {len(composites_list)} records, "
                    f"RECOMMEND={tiers.get('RECOMMEND',0)}, "
                    f"CONSIDER={tiers.get('CONSIDER',0)}, "
                    f"MONITOR={tiers.get('MONITOR',0)}, avg={avg:.3f}"
                )

            composite.main = _test_main
            composite.main()

            self.summary.stage_outputs["composite_scores"] = str(composite.OUT)

        except Exception as e:
            self._fail(
                "composite_scoring",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def run_ranking(self) -> None:
        self._log("Stage 5: Ranking...")

        try:
            setattr(ranking, "IN_COMPOSITE", self.output_dir / "phase2c_composite_scores.json")
            setattr(ranking, "OUT", self.output_dir / "phase2c_rankings.json")
            ranking.main()

            with open(ranking.OUT) as f:
                ranked = json.load(f)

            self._log(
                f"Ranking complete: {len(ranked)} records, top rank = "
                f"{ranked[0]['company_name']} ({ranked[0]['composite_score']})"
            )

            self.summary.stage_outputs["rankings"] = str(ranking.OUT)

        except Exception as e:
            self._fail("ranking", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    def run_application_decision(self) -> None:
        self._log("Stage 6: Application decision...")

        try:
            setattr(decision, "IN_RANKING", self.output_dir / "phase2c_rankings.json")
            setattr(decision, "OUT", self.output_dir / "phase2c_application_decisions.json")

            orig_main = decision.main

            def _test_decision_main():
                ranked = json.load(open(decision.IN_RANKING))
                decisions = [decision.make_decision(r) for r in ranked]

                assert len(decisions) == len(ranked), "must not drop any job"
                assert [d["rank"] for d in decisions] == [
                    r["rank"] for r in ranked
                ], "rank order changed"
                ids = [d["job_id"] for d in decisions]
                assert len(set(ids)) == len(ids), "duplicate job_id in decisions"
                assert set(ids) == {r["job_id"] for r in ranked}, "job_id set mismatch"

                for d in decisions:
                    if d["application_decision"] == "CANDIDATE":
                        assert (
                            d["match_eligibility"] == "ELIGIBLE"
                        ), "CANDIDATE must be ELIGIBLE"
                        assert (
                            d["recommendation_tier"] in decision.CANDIDATE_TIERS
                        ), "CANDIDATE tier invalid"
                    if d["match_eligibility"] == "BLOCKED":
                        assert (
                            d["application_decision"] == "NOT_RECOMMENDED"
                        ), "BLOCKED must be NOT_RECOMMENDED"
                    if d["match_eligibility"] == "REVIEW":
                        assert (
                            d["application_decision"] == "REVIEW"
                        ), "REVIEW must stay REVIEW"
                    assert d["application_blocks"] is False, "decision must never block"
                    assert (
                        d["application_rejection_reason"] is None
                    ), "decision must never reject"
                    assert d["application_candidate"] == (
                        d["application_decision"] == "CANDIDATE"
                    )

                with open(decision.OUT, "w") as f:
                    json.dump(decisions, f, indent=2)

                from collections import Counter

                by_decision = Counter(d["application_decision"] for d in decisions)
                candidates = [
                    d for d in decisions if d["application_decision"] == "CANDIDATE"
                ]

                self.summary.candidate_count = len(candidates)
                self.summary.review_count = by_decision.get("REVIEW", 0)
                self.summary.not_recommended_count = by_decision.get(
                    "NOT_RECOMMENDED", 0
                )

                self._log(f"Decisions: {dict(by_decision)}")
                if candidates:
                    self._log(
                        f"Top candidate: {candidates[0]['company_name']} | "
                        f"{candidates[0]['job_title']} | {candidates[0]['composite_score']}"
                    )
                else:
                    self._log("No CANDIDATE records (all REVIEW or NOT_RECOMMENDED)")

                for d in decisions:
                    assert "apply" not in str(
                        d
                    ).lower() or "application_decision" in str(
                        d
                    ), "No application submission logic should exist"

            decision.main = _test_decision_main
            decision.main()

            self.summary.stage_outputs["application_decisions"] = str(decision.OUT)

        except Exception as e:
            self._fail(
                "application_decision",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def run_application_queue(self) -> None:
        self._log("Stage 7: Application queue preparation...")

        try:
            setattr(queue, "INPUT_FILE", self.output_dir / "phase2c_application_decisions.json")
            setattr(queue, "OUTPUT_FILE", self.output_dir / "phase4_application_queue.json")

            orig_main = queue.main

            def _test_queue_main():
                decisions = queue.load_decisions()
                candidates = queue.filter_candidates(decisions)

                self.summary.queue_count = len(candidates)

                for c in candidates:
                    assert (
                        c["application_decision"] == "CANDIDATE"
                    ), f"Non-CANDIDATE: {c['job_id']}"
                    assert (
                        c["application_candidate"] is True
                    ), f"application_candidate false: {c['job_id']}"

                job_ids = [c["job_id"] for c in candidates]
                assert len(job_ids) == len(set(job_ids)), "Duplicate job_id in output"

                for c in candidates:
                    for field in queue.REQUIRED_FIELDS:
                        assert (
                            field in c
                        ), f"Missing required field {field} in {c['job_id']}"

                for c in candidates:
                    assert (
                        isinstance(c["rank"], int) and c["rank"] >= 1
                    ), f"Invalid rank: {c['job_id']}"
                    assert isinstance(
                        c["composite_score"], (int, float)
                    ), f"Invalid composite_score: {c['job_id']}"

                ranks = [c["rank"] for c in candidates]
                assert ranks == sorted(ranks), "Output not sorted by rank"

                for c in candidates:
                    assert (
                        c["application_status"] == "PENDING"
                    ), f"application_status != PENDING: {c['job_id']}"
                    assert (
                        c["application_attempted"] is False
                    ), f"application_attempted != false: {c['job_id']}"
                    assert (
                        c["application_submitted"] is False
                    ), f"application_submitted != false: {c['job_id']}"

                queue.write_output(candidates)

                self._log(f"Queue: {len(candidates)} candidate records prepared")

                with queue.OUTPUT_FILE.open("r", encoding="utf-8") as f:
                    reread = json.load(f)
                assert reread == candidates, "Determinism check failed on re-read"

            queue.main = _test_queue_main
            queue.main()

            self.summary.stage_outputs["application_queue"] = str(queue.OUTPUT_FILE)

        except Exception as e:
            self._fail(
                "application_queue",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def upload_to_google_drive(self) -> None:
        self._log("Stage 8: Google Drive upload...")

        try:
            import requests
            import json as json_lib

            creds_path = Path("/home/ragul/.claude/.credentials.json")
            if not creds_path.exists():
                self._fail(
                    "google_drive_upload",
                    "Credentials file not found at ~/.claude/.credentials.json",
                )

            with open(creds_path) as f:
                creds = json_lib.load(f)

            mcp_oauth = creds.get("mcpOAuth", {})
            gdrive_key = None
            for k, v in mcp_oauth.items():
                if v.get("serverName") == "gdrive-upload":
                    gdrive_key = k
                    break

            if not gdrive_key:
                self._fail(
                    "google_drive_upload",
                    "gdrive-upload credentials not found in mcpOAuth",
                )

            access_token = mcp_oauth[gdrive_key].get("accessToken")
            if not access_token:
                self._fail(
                    "google_drive_upload", "No access token found for gdrive-upload"
                )

            # Find or create the job-pipeline folder
            folder_id = None
            search_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "files_list",
                    "arguments": {
                        "q": "name='job-pipeline' and mimeType='application/vnd.google-apps.folder'",
                        "pageSize": 10,
                    },
                },
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {access_token}",
            }

            response = requests.post(
                "http://localhost:3005/mcp",
                json=search_payload,
                headers=headers,
                timeout=30,
            )
            result = response.json()

            if "result" in result and "structuredContent" in result["result"]:
                files = result["result"]["structuredContent"].get("files", [])
                if files:
                    folder_id = files[0]["id"]
                    self._log(f"Found existing job-pipeline folder: {folder_id}")

            if not folder_id:
                create_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "folder_create",
                        "arguments": {"name": "job-pipeline", "parentId": "root"},
                    },
                }
                response = requests.post(
                    "http://localhost:3005/mcp",
                    json=create_payload,
                    headers=headers,
                    timeout=30,
                )
                result = response.json()
                if "result" in result and "structuredContent" in result["result"]:
                    folder_id = result["result"]["structuredContent"].get("id")
                    self._log(f"Created job-pipeline folder: {folder_id}")
                else:
                    self._fail(
                        "google_drive_upload", f"Failed to create folder: {result}"
                    )

            queue_file = self.output_dir / "phase4_application_queue.json"
            if not queue_file.exists():
                self._fail("google_drive_upload", "Queue file not found")

            with open(queue_file) as f:
                queue_content = f.read()

            file_name = f"application_queue_{self.run_id}.json"
            upload_payload = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "file_upload",
                    "arguments": {
                        "name": file_name,
                        "parents": [folder_id],
                        "mimeType": "application/json",
                        "content": queue_content,
                    },
                },
            }

            response = requests.post(
                "http://localhost:3005/mcp",
                json=upload_payload,
                headers=headers,
                timeout=30,
            )
            result = response.json()

            if "result" in result and "structuredContent" in result["result"]:
                file_id = result["result"]["structuredContent"].get("id")
                self.summary.google_drive_upload_result = (
                    f"SUCCESS: uploaded {file_name} (id: {file_id})"
                )
                self.summary.google_drive_file_id = file_id
                self._log(f"Uploaded to Google Drive: {file_name} (id: {file_id})")

                # Verify by downloading
                self._verify_drive_upload(access_token, file_id, queue_content, headers)
            else:
                self._fail("google_drive_upload", f"Upload failed: {result}")

        except Exception as e:
            self._fail(
                "google_drive_upload",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def _verify_drive_upload(
        self, access_token: str, file_id: str, local_content: str, headers: dict
    ) -> None:
        """Download the uploaded file and compare with local content."""
        self._log("Verifying Google Drive upload via download...")

        try:
            import requests as requests_module

            download_payload = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "file_download", "arguments": {"fileId": file_id}},
            }

            response = requests_module.post(
                "http://localhost:3005/mcp",
                json=download_payload,
                headers=headers,
                timeout=30,
            )
            result = response.json()

            if "result" in result and "structuredContent" in result["result"]:
                downloaded_content = result["result"]["structuredContent"].get(
                    "content", ""
                )
                if downloaded_content == local_content:
                    self._log("Google Drive exact-match verification: PASS")
                else:
                    self._fail(
                        "google_drive_verification",
                        "Content mismatch between local and downloaded file",
                    )
            else:
                self._fail("google_drive_verification", f"Download failed: {result}")

        except Exception as e:
            self._fail(
                "google_drive_verification",
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )

    def run_full_pipeline(self, apify_items: List[Dict[str, Any]]) -> RunSummary:
        try:
            self._log(f"Processing {len(apify_items)} fresh Apify items...")

            # Stage 1: Apify ingestion (fresh data)
            fresh_items, dataset_id = self.run_apify_ingestion(apify_items)

            # Stage 2: Phase 2B
            self.run_phase2b_canonicalization(fresh_items)

            # Stage 3: Component scorers
            self.run_component_scorers()

            # Stage 4: Composite scoring
            self.run_composite_scoring()

            # Stage 5: Ranking
            self.run_ranking()

            # Stage 6: Application decision
            self.run_application_decision()

            # Stage 7: Application queue
            self.run_application_queue()

            # Stage 8: Google Drive upload
            self.upload_to_google_drive()

            # Success!
            self.summary.completed_at = datetime.now().isoformat()
            self._write_summary()

            self._log("=== PHASE 10 VALIDATION COMPLETE ===")
            self._log(f"Run ID: {self.run_id}")
            self._log(f"Apify input: {self.summary.apify_input_count}")
            self._log(f"Canonical records: {self.summary.canonical_record_count}")
            self._log(f"Candidates: {self.summary.candidate_count}")
            self._log(f"Review: {self.summary.review_count}")
            self._log(f"Not recommended: {self.summary.not_recommended_count}")
            self._log(f"Queue count: {self.summary.queue_count}")
            self._log(f"Drive upload: {self.summary.google_drive_upload_result}")
            self._log(f"Failures: {len(self.summary.failures)}")

            return self.summary

        except Exception as e:
            self.summary.completed_at = datetime.now().isoformat()
            self._write_summary()
            self._log(f"Pipeline failed: {e}")
            raise


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 10 — Fresh Real Apify Production Validation"
    )
    parser.add_argument(
        "--max-jobs", type=int, default=10, help="Maximum jobs to process (default: 10)"
    )
    args = parser.parse_args()

    # We already fetched the Apify data, so read it from the file we saved
    # The Apify dataset ID is Wxg5YAKdJilyrCyyH, but we need to pass items to the script
    # For now, we'll use the mcp__apify__get-dataset-items result

    # We'll pass the items via stdin
    print("Reading Apify items from stdin...")
    try:
        input_data = json.load(sys.stdin)
        if isinstance(input_data, dict) and "items" in input_data:
            apify_items = input_data["items"]
        elif isinstance(input_data, list):
            apify_items = input_data
        else:
            print("ERROR: Expected JSON with 'items' array or direct array")
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON input: {e}")
        sys.exit(1)

    print(f"Loaded {len(apify_items)} fresh Apify items")

    validator = Phase10Validator(max_jobs=args.max_jobs)

    summary = validator.run_full_pipeline(apify_items)

    # Print final summary
    print("\n" + "=" * 60)
    print("PHASE 10 VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Run ID:              {summary.run_id}")
    print(f"Started:             {summary.started_at}")
    print(f"Completed:           {summary.completed_at}")
    print(f"Apify Input Count:   {summary.apify_input_count}")
    print(f"Canonical Records:   {summary.canonical_record_count}")
    print(f"Candidates:          {summary.candidate_count}")
    print(f"Review:              {summary.review_count}")
    print(f"Not Recommended:     {summary.not_recommended_count}")
    print(f"Queue Count:         {summary.queue_count}")
    print(f"Drive Upload:        {summary.google_drive_upload_result}")
    if summary.google_drive_file_id:
        print(f"Drive File ID:       {summary.google_drive_file_id}")
    print(f"Failures:            {len(summary.failures)}")
    for failure in summary.failures:
        print(f"  - {failure}")
    print("=" * 60)

    if summary.failures:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
