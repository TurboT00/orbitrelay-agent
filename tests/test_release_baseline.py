import copy
import json
import unittest

from scripts.verify_release_baseline import (
    ContractError,
    contract_path,
    load_contract,
    validate_contract,
)


class ReleaseBaselineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(contract_path())

    def test_published_contract_is_complete_and_valid(self) -> None:
        validate_contract(self.contract)

    def test_omitted_finding_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["findings"].pop()

        with self.assertRaisesRegex(ContractError, "finding registry mismatch"):
            validate_contract(contract)

    def test_duplicate_finding_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["findings"].append(copy.deepcopy(contract["findings"][0]))

        with self.assertRaisesRegex(ContractError, "duplicate finding"):
            validate_contract(contract)

    def test_stale_evidence_cannot_close_a_finding(self) -> None:
        contract = copy.deepcopy(self.contract)
        fixed = next(item for item in contract["findings"] if item["status"] == "fixed")
        evidence_id = fixed["evidence_ids"][0]
        evidence = next(item for item in contract["evidence"] if item["id"] == evidence_id)
        evidence["revision"] = "0" * 40

        with self.assertRaisesRegex(ContractError, "stale evidence"):
            validate_contract(contract)

    def test_different_existing_assessment_revision_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        older_revision = "ad2e55611c3a0bd2c764b30f7875bb1454acc710"
        contract["assessment"]["revision"] = older_revision
        for evidence in contract["evidence"]:
            evidence["revision"] = older_revision
            evidence["references"] = [{"path": "pyproject.toml", "locator": "project metadata"}]

        with self.assertRaisesRegex(ContractError, "unexpected assessed revision"):
            validate_contract(contract)

    def test_unverifiable_passed_evidence_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        evidence = next(item for item in contract["evidence"] if item["outcome"] == "passed")
        evidence["command"] = "curl https://example.invalid/live-provider-probe"

        with self.assertRaisesRegex(ContractError, "unapproved passed evidence command"):
            validate_contract(contract)

    def test_contract_contains_only_automated_release_evidence(self) -> None:
        serialized = json.dumps(self.contract, sort_keys=True).lower()

        self.assertEqual(
            set(self.contract),
            {"schema_version", "story_id", "assessment", "summary", "evidence", "findings", "release_version"},
        )
        self.assertNotRegex(serialized, r"\bmt-\d{2}\b")

    def test_release_version_records_selected_stabilization_identity(self) -> None:
        release = self.contract["release_version"]

        self.assertEqual(release["state"], "selected")
        self.assertEqual(release["selected"], "0.6.0")

    def test_contract_contains_no_secret_bearing_evidence(self) -> None:
        serialized = json.dumps(self.contract, sort_keys=True)

        self.assertNotIn("PRIVATE_TOKEN=", serialized)
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", serialized)
        self.assertNotIn("Bearer ", serialized)
        self.assertNotIn("workspace-secret", serialized)

    def test_injected_secret_and_private_payload_are_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["findings"][0]["rationale"] += (
            ' {"OPENAI_API_KEY":"opaque-example-value",'
            '"private_payload":{"account_data":"private-example-value"}}'
        )

        with self.assertRaisesRegex(ContractError, "secret-bearing"):
            validate_contract(contract)

    def test_summary_matches_published_dispositions(self) -> None:
        expected_counts: dict[str, int] = {}
        for finding in self.contract["findings"]:
            expected_counts[finding["status"]] = expected_counts.get(finding["status"], 0) + 1
        expected_blockers = sorted(
            finding["id"] for finding in self.contract["findings"] if finding["status"] == "open"
        )

        self.assertEqual(self.contract["summary"]["counts"], expected_counts)
        self.assertEqual(self.contract["summary"]["release_blockers"], expected_blockers)

    def test_required_disposition_cannot_be_reclassified_with_its_summary(self) -> None:
        contract = copy.deepcopy(self.contract)
        finding = next(item for item in contract["findings"] if item["status"] == "fixed")
        finding_id = finding["id"]
        previous = finding["status"]
        finding["status"] = "accepted"
        contract["summary"]["counts"]["accepted"] = (
            contract["summary"]["counts"].get("accepted", 0) + 1
        )
        contract["summary"]["counts"][previous] -= 1
        if contract["summary"]["counts"][previous] == 0:
            del contract["summary"]["counts"][previous]

        with self.assertRaisesRegex(
            ContractError, f"unexpected disposition for {finding_id}"
        ):
            validate_contract(contract)

    def test_evidence_reference_mutation_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["evidence"][0]["references"] = [
            {"path": "pyproject.toml", "locator": "unrelated but valid repository file"}
        ]

        with self.assertRaisesRegex(ContractError, "contract content does not match"):
            validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
