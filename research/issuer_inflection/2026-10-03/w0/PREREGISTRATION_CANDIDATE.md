# I3 W0 preregistration candidate — frozen before validation/holdout body inspection

**Status: CANDIDATE_NOT_REGISTERED / BODY_INSPECTION_NOT_AUTHORIZED / OUTCOME_INSPECTION_NOT_AUTHORIZED.**

This is the complete W0 scientific freeze that can be prepared without mutating the canonical Research/Brain experiment registry. It is subordinate to the audited `VALIDATION_AND_ACCEPTANCE.md` at commissioning commit `11a64ce93328d5248967987be0d2a51883765797`. It does not create an experiment ID, grant source rights, authorize body inspection, assign a prospective holdout event, or claim any R/C/U/P result.

The machine-readable block below is deliberately embedded in Markdown so it remains part of the existing I3 review capsule without changing the repository-wide runtime/evidence path classification. `test_i3_preregistration_candidate.py` parses and validates this exact block.

<!-- I3_PREREG_JSON_BEGIN -->
```json
{
  "schema": "issuer_inflection.preregistration_candidate/v1",
  "program": "issuer-inflection-intelligence",
  "operation_id": "i3-w0-issuer-inflection-20261003-astra-c4",
  "parent_carrier": "Mastermind#1183",
  "child_carrier": "Mastermind#1195",
  "commission_commit": "11a64ce93328d5248967987be0d2a51883765797",
  "validation_contract_sha": "7c6a036b4ec8f452b69efd2764e77f0b5e118078",
  "masterplan_sha": "1db62f0dd94f1e1cf3898377129ff39af58fe774",
  "candidate_state": "NOT_REGISTERED",
  "trial_registered": false,
  "body_inspection_authorized": false,
  "outcome_inspection_authorized": false,
  "production_emission_authorized": false,
  "authority": {
    "class": "research_only_candidate",
    "may_rank": false,
    "may_gate": false,
    "may_size": false,
    "may_originate": false,
    "may_open_entry": false,
    "may_trade": false,
    "may_modify_prophet": false
  },
  "owner_plane": {
    "program": "portfolio-learning-accountability",
    "repository": "Mastermind",
    "registry_module": "brain/experiment_registry.py",
    "registry_module_blob": "21e19915d99340659b78e8b7ff7f86e3e48a5f74",
    "registry_data_blob": "b79bffd072b240bc0384c1653ca5b7fbf56624ed",
    "runtime_writer_admitted": false,
    "serialized_mutation_fence_proven": false,
    "post_write_readback_proven": false,
    "owner_dependency": "Mastermind#773 issuecomment-5978424457"
  },
  "immutable_inputs": {
    "transition_schema_sha256": "9d9931a439c0f639f8bbdeeef0f600834ec974036d834448627010fbb381fd33",
    "comparator_definition_sha256": "9ed1d94937fda6755caecdb04fcc4c6777b91762a9d9ebaea5bdedbff6b02209",
    "beta_event_selection_schema": "issuer_inflection.beta_event_identity_candidate/v1",
    "beta_event_selection_sha256": "d64bf572890c411e3cb9f2cf8adacdee48b6f2481c2f0ce9defe737072274a9b",
    "beta_pit_witness_file_sha256": "a88c03741c3c9976d686f1905e83c103d18a3485addccd732cdc239cf0dfe876",
    "corpus_identity_file_sha256": "5d581797edbf27e680595df10d64a61e26403734584f97c5aad9f245407bba58"
  },
  "source_owners": {
    "earnings_event_metadata": {
      "owner": "earnings-intelligence",
      "merge_commit": "d4e7c3788d674d43be57e0cbc017f858b832c9f1",
      "source_pr": "macro#8392",
      "parquet_sha256": "5309ece0cd66b33d69abb8055afa05333d00bcfb43ace87d7997b3655946446f",
      "filing_identity": "exact_(CIK,accession)",
      "event_identity": "exact_(CIK,report_date)"
    },
    "pit_membership": {
      "path": "data/breadth/sp1500_pit_membership.parquet",
      "git_blob": "ec7085bc7460aca4a07661fa5983c424e1559be8",
      "sha256": "7b34316c0561619ba052f02036ec1fbe7fff3d00dcda3e7acb7dffda10582eca"
    },
    "financial_lineage": {
      "owner": "fundamental-forensics",
      "merge_commit": "4294fd498e8c31cb72424e34b8769a48b1f0afd2",
      "lineage_disclosure_trusted_for_i3_refs": false,
      "reason": "query-time validation does not yet require exact equality of the full positive-evidence payload to live owner occurrence groups"
    },
    "rights": {
      "owner": "gmi-theme-graph/shared-rights",
      "source_law_status": "SEC_EDGAR_REUSE_SUPPORTED_BY_EXISTING_SOURCE_RIGHTS_REGISTER",
      "runtime_purpose_binding": "NOT_ADMITTED",
      "protected_runtime_has_sec_edgar_family": false
    }
  },
  "corpus": {
    "split_unit": "issuer_time_source_revision_family",
    "random_row_split_forbidden": true,
    "dependence_groups_keep_together": [
      "amendments_and_original_filing_family",
      "syndicated_or_duplicate_source_copies",
      "dual_class_events_sharing_load_bearing_filing",
      "repeated_comparisons_sharing_load_bearing_filing"
    ],
    "development_exposed": [
      "AAPL",
      "PG",
      "IMCE/homebuilder studied family"
    ],
    "beta_prebody_candidates": {
      "count": 12,
      "selection_sha256": "d64bf572890c411e3cb9f2cf8adacdee48b6f2481c2f0ce9defe737072274a9b",
      "pit_membership_qualified_count": 12,
      "body_reads": 0,
      "outcome_reads": 0,
      "registered_event_assignments": 0,
      "historical_business_family_qualified": false,
      "current_proxy_is_discovery_only": true,
      "classification_use_state": "BLOCKED_BEFORE_BODY_INSPECTION_UNTIL_OWNER_REGISTRATION_AND_FAMILY_SCOPE_DECISION"
    },
    "prospective_temporal_holdout_candidates": {
      "ticker_count": 12,
      "event_identity_state": "FUTURE_UNASSIGNED",
      "body_reads": 0,
      "outcome_reads": 0,
      "selection_rule": "only an eligible event strictly after the frozen preselection time and before body inspection may be assigned"
    },
    "reserve_candidates": {
      "count": 6,
      "body_reads": 0,
      "outcome_reads": 0
    },
    "sealed_external_holdout": {
      "e3_eight_revision_corpus": "EXCLUDED_DO_NOT_OPEN"
    },
    "replacement_rule": "same-proxy deterministic replacement is permitted only before body/outcome inspection; exclusion remains in the denominator",
    "historical_eligibility_rule": "current index/industry membership cannot certify historical eligibility; use event-date PIT membership and event-time owner-qualified family metadata or record the scope as unstratified/unsupported"
  },
  "labeling": {
    "validation_and_holdout_annotators": 2,
    "independent_source_qualified": true,
    "future_price_outcomes_hidden": true,
    "candidate_output_hidden": true,
    "disagreement_rule": "third_adjudication_or_retain_unresolved",
    "missing_or_ambiguous_label_is_valid": true,
    "record": [
      "agreement",
      "label_confidence",
      "reason"
    ]
  },
  "tracks": {
    "R": {
      "question": "Does reconstruction preserve exactly what was available and admitted at the requested cutoff?",
      "hypothesis": "The same frozen inputs and method reproduce the same canonical derived truth/refusal while preserving owner identities, rights, revisions and clocks.",
      "falsifier": "Any accepted wrong-issuer, future-input, forbidden-rights, authority-widening, mixed-generation or non-reproducible deterministic result.",
      "primary_gate": "all load-bearing owner references and T01-T30 applicable invariants pass with exact refusal families and zero forbidden accepted cases",
      "coverage_floor": 0.80,
      "coverage_denominator": "predeclared supported/evaluable universe only; rights-denied and unsupported-source counts remain visible outside the denominator"
    },
    "C": {
      "question": "Does the frozen qualified-change rule classify the measured economic/reporting change correctly?",
      "hypothesis": "For owner-qualified supported classes, the frozen rule attains high precision without hiding refusals or dependence.",
      "falsifier": "Precision/recall/lower-bound gates fail, required positive/negative controls are absent, dependence defeats the claimed inference, or an unsupported stratum is represented as covered.",
      "precision_min": 0.95,
      "recall_min": 0.80,
      "precision_lower_95_bound_min": 0.85,
      "predicted_positive_independent_units_min": 100,
      "adjudicated_positive_independent_units_min": 100,
      "dependence_aware_uncertainty": true,
      "per_family_confusion_and_coverage_required": true,
      "underpowered_is_not_pass": true
    },
    "U": {
      "question": "Does I3 improve analysts' source-correct understanding of the evidence versus credible baselines?",
      "state": "CHILD_PREREG_REQUIRED_BEFORE_UTILITY_OUTCOMES",
      "baselines": [
        "B0_static_latest_financial_context",
        "B1_simple_same_basis_deltas",
        "B2_source_cited_event_summary",
        "B3_full_i3_composition"
      ],
      "primary_outcome": "source_correct_answer_quality_on_prewritten_rubric",
      "minimum_decision_useful_effect_absolute": 0.10,
      "primary_interval_must_exclude_no_improvement": true,
      "secondary_median_time_reduction_min": 0.20,
      "unsupported_conclusions_must_not_increase": true,
      "pilot_required_for_power_and_sample_size": true,
      "pilot_reuse_in_confirmatory_trial": false,
      "current_confirmatory_sample_size_frozen": false
    },
    "P": {
      "question": "Does a named feature improve a separately specified future fundamental or market outcome beyond admitted baselines?",
      "state": "NO_PREDICTIVE_TRIAL_REGISTERED_IN_W0",
      "universal_alpha_threshold": null,
      "feature_specific_economic_target_required": true,
      "feature_specific_power_sensitivity_required": true,
      "future_fundamental_and_market_outcomes_separate": true,
      "minimum_baselines": [
        "static_fundamentals",
        "simple_financial_deltas",
        "existing_price_technical_theme_context"
      ],
      "walk_forward_or_prospective_required": true,
      "train_only_fit_and_normalization": true,
      "embargo_or_purge_when_windows_overlap": true,
      "decision_path_influence": false
    }
  },
  "multiplicity": {
    "tracks_remain_separate": true,
    "no_aggregate_success_score": true,
    "classification_primary_gate_is_joint_threshold_based": true,
    "utility_primary_comparison": "B3_vs_strongest_predeclared_baseline",
    "utility_ablations_are_secondary": true,
    "formal_confirmatory_secondary_family_control": "Holm",
    "predictive_child_prereg": "declare Holm for confirmatory families or a justified FDR procedure for explicitly exploratory screens before outcome inspection"
  },
  "stopping": {
    "adaptive_stop_for_favorable_result": false,
    "stop_for_safety_rights_or_corrupt_input": true,
    "classification_claim_requires_minimum_independent_units": true,
    "unmatured_outcomes_are_not_zero": true,
    "insufficient_power_disposition": "UNDERPOWERED",
    "validation_case_used_for_method_repair_becomes": "DEVELOPMENT_EVIDENCE"
  },
  "exposure_capture": {
    "capture_begins_with_w1": true,
    "input_revision": "REQUIRED",
    "requested_cutoff": "REQUIRED",
    "mode_emitted_or_reconstructed": "REQUIRED",
    "method_identity": "REQUIRED",
    "transition_or_refusal_identity": "REQUIRED",
    "later_correction_identity": "REQUIRED",
    "outcome_readiness": "REQUIRED",
    "ui_display_event": "SEPARATE_REQUIRED_IF_USED",
    "machine_model_receipt": "SEPARATE_REQUIRED_IF_USED",
    "alert_emission_event": "SEPARATE_REQUIRED_IF_USED",
    "runtime_exposure_writer_admitted": false
  },
  "rights_purposes": {
    "public_display": "NOT_RUNTIME_BOUND",
    "internal_use": "SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND",
    "model_context": "SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND",
    "historical_research": "SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND",
    "unknown_or_revoked_blocks_use": true
  },
  "amendment": {
    "new_version_required": true,
    "reason_required": true,
    "prior_result_visibility_required": true,
    "silent_replacement_forbidden": true,
    "repaired_validation_case_becomes_development": true,
    "fresh_holdout_required_after_holdout_contamination": true
  },
  "open_registration_gates": [
    "canonical_registry_serialized_writer_and_post_write_readback",
    "historical_beta_family_scope_owner_decision_or_explicit_unstratified_amendment",
    "purpose_specific_runtime_rights_binding_before_body_use",
    "independent_architecture_source_owner_acceptance"
  ]
}
```
<!-- I3_PREREG_JSON_END -->

## Interpretation

This candidate intentionally freezes **what cannot yet be claimed**. The twelve beta event identities are source- and PIT-qualified metadata candidates, not registered validation examples. The twelve prospective holdout names still have no event identities and therefore remain untouched by construction. The confirmatory classification gate cannot be declared adequately observed until the independent-unit minima are met; the present twelve-name beta pool is a coverage/pilot floor, not statistical validation.

Utility and predictive work each require their own child preregistration before outcome inspection. For utility, the audited contract explicitly requires a pilot to choose power/sample size and forbids reusing that pilot as confirmatory data. For prediction, the program intentionally has no universal alpha threshold: every named feature must freeze its own economically meaningful target, horizon, executable timing, costs, dependence and power assumptions.

No body or outcome should be inspected merely because this document exists. Registration through the existing Portfolio Learning and Accountability owner, purpose-specific rights admission, and the explicit beta-family scope decision remain hard gates.
