"""Static synthetic reference tables (labs, people, resources, SKUs, policies).

Values named in docs/05-DATA-FIXTURES.md are copied exactly. Values the docs
leave open are marked `# assumption` and listed in data_gen/README.md.
"""
from .scenario import PROVENANCE

DEPARTMENTS = [
    {"department_id": "dept_life_sciences_demo", "name": "Life Sciences (synthetic)",
     "building_id": "north_bio_building", "building_name": "North Bio Building"},
]

LABS = [
    {"lab_id": "lab_moreno", "name": "Moreno Cell Biology", "department_id": "dept_life_sciences_demo", "manager_id": "moreno_mgr"},
    {"lab_id": "lab_chen", "name": "Chen Imaging", "department_id": "dept_life_sciences_demo", "manager_id": "chen_owner"},
    {"lab_id": "lab_patel", "name": "Patel Neurobiology", "department_id": "dept_life_sciences_demo", "manager_id": "patel_mgr"},
    {"lab_id": "lab_rivera", "name": "Rivera Genetics", "department_id": "dept_life_sciences_demo", "manager_id": "rivera_mgr"},
]

# role values: researcher | lab_manager | core_scheduler | department_admin
PERSONS = [
    {"person_id": "morgan", "display_name": "Morgan (synthetic)", "lab_id": "lab_moreno", "role": "researcher",
     "qualifications": ["confocal_cert", "wet_prep"]},
    {"person_id": "moreno_mgr", "display_name": "Moreno lab manager (synthetic)", "lab_id": "lab_moreno", "role": "lab_manager",
     "qualifications": ["confocal_cert", "wet_prep"]},
    # Chen is the booking owner who approves the move; manager of Chen Imaging.  # assumption
    {"person_id": "chen_owner", "display_name": "Chen (synthetic)", "lab_id": "lab_chen", "role": "lab_manager",
     "qualifications": ["confocal_cert", "wet_prep"]},
    # Extra synthetic users so the 8 movable Confocal-1 hours have qualified owners.  # assumption
    {"person_id": "sam_chen", "display_name": "Sam (synthetic)", "lab_id": "lab_chen", "role": "researcher",
     "qualifications": ["confocal_cert", "confocal_2_cert", "wet_prep"]},
    {"person_id": "patel_mgr", "display_name": "Patel lab manager (synthetic)", "lab_id": "lab_patel", "role": "lab_manager",
     "qualifications": ["flow_cert", "wet_prep"]},
    {"person_id": "jordan_patel", "display_name": "Jordan (synthetic)", "lab_id": "lab_patel", "role": "researcher",
     "qualifications": ["flow_cert", "pcr_basic", "wet_prep"]},
    {"person_id": "rivera_mgr", "display_name": "Rivera lab manager (synthetic)", "lab_id": "lab_rivera", "role": "lab_manager",
     "qualifications": ["pcr_basic", "sequencer_cert", "wet_prep"]},
    {"person_id": "riley_rivera", "display_name": "Riley (synthetic)", "lab_id": "lab_rivera", "role": "researcher",
     "qualifications": ["confocal_cert", "confocal_2_cert", "flow_cert", "pcr_basic", "wet_prep"]},
    {"person_id": "core_sched", "display_name": "Core scheduler (synthetic)", "lab_id": "", "role": "core_scheduler",
     "qualifications": []},
    {"person_id": "dept_admin", "display_name": "Department admin (synthetic)", "lab_id": "", "role": "department_admin",
     "qualifications": []},
]

INSTRUMENTS = [
    {"instrument_id": "confocal_1", "name": "Confocal Microscope 1", "kind": "confocal_microscope",
     "capabilities": ["gfp_imaging", "confocal_imaging"], "required_qualifications": ["confocal_cert"], "buffer_minutes": 15},
    {"instrument_id": "confocal_2", "name": "Confocal Microscope 2", "kind": "confocal_microscope",
     "capabilities": ["gfp_imaging", "confocal_imaging"], "required_qualifications": ["confocal_2_cert"], "buffer_minutes": 15},
    {"instrument_id": "flow_1", "name": "Flow Cytometer 1", "kind": "flow_cytometer",
     "capabilities": ["flow_analysis"], "required_qualifications": ["flow_cert"], "buffer_minutes": 20},
    {"instrument_id": "flow_2", "name": "Flow Cytometer 2", "kind": "flow_cytometer",
     "capabilities": ["flow_analysis"], "required_qualifications": ["flow_cert"], "buffer_minutes": 20},
    {"instrument_id": "pcr_1", "name": "Thermal Cycler 1", "kind": "thermal_cycler",
     "capabilities": ["pcr"], "required_qualifications": ["pcr_basic"], "buffer_minutes": 0},  # assumption
    {"instrument_id": "pcr_2", "name": "Thermal Cycler 2", "kind": "thermal_cycler",
     "capabilities": ["pcr"], "required_qualifications": ["pcr_basic"], "buffer_minutes": 0},  # assumption
    {"instrument_id": "centrifuge_1", "name": "High-speed Centrifuge", "kind": "centrifuge",
     "capabilities": ["high_g_centrifugation"], "required_qualifications": [], "buffer_minutes": 10},  # assumption
    {"instrument_id": "plate_reader_1", "name": "Plate Reader", "kind": "plate_reader",
     "capabilities": ["fluorescence_plate_read"], "required_qualifications": [], "buffer_minutes": 0},  # assumption
    {"instrument_id": "sequencer_1", "name": "Benchtop Sequencer", "kind": "sequencer",
     "capabilities": ["sequencing"], "required_qualifications": ["sequencer_cert"], "buffer_minutes": 15},  # assumption
    {"instrument_id": "microscope_wide_1", "name": "Widefield Fluorescence Microscope", "kind": "widefield_microscope",
     "capabilities": ["gfp_imaging", "widefield_imaging"], "required_qualifications": [], "buffer_minutes": 10},  # assumption
]
for _inst in INSTRUMENTS:
    _inst.update({"location": "north_bio_building", "staffed_hours_per_week": 40,
                  "open_local": "09:00", "close_local": "17:00", "status": "active"})

ROOMS = [
    {"room_id": "prep_a", "name": "Prep Room A", "kind": "wet_prep", "capacity": 4,
     "capabilities": ["wet_prep"], "buffer_minutes": 10},
    {"room_id": "prep_b", "name": "Prep Room B", "kind": "wet_prep", "capacity": 4,
     "capabilities": ["wet_prep"], "buffer_minutes": 10},  # assumption: same turnover as prep_a
    {"room_id": "analysis_room", "name": "Analysis Room", "kind": "dry_analysis", "capacity": 6,
     "capabilities": ["dry_analysis"], "buffer_minutes": 0},  # assumption
    {"room_id": "consult_room", "name": "Consult Room", "kind": "meeting", "capacity": 8,
     "capabilities": ["meeting"], "buffer_minutes": 0},  # assumption
]
for _room in ROOMS:
    _room.update({"location": "north_bio_building", "open_local": "09:00", "close_local": "17:00"})

VENDORS = [
    {"vendor_id": "vendor_bioreagent", "name": "BioReagent Supply (synthetic)"},
    {"vendor_id": "vendor_glassco", "name": "GlassCo Labware (synthetic)"},
    {"vendor_id": "vendor_labbasics", "name": "LabBasics (synthetic)"},
]

# tier_min_qty / tier_price empty means no volume tier.
SUPPLY_SKUS = [
    {"sku_id": "ANTI_GFP_100", "name": "Anti-GFP antibody pack", "vendor_id": "vendor_bioreagent", "unit": "pack",
     "base_price_usd": 120, "tier_min_qty": 5, "tier_price_usd": 105, "shipping_per_order_usd": 20,
     "lead_business_days": 2, "storage": "frozen_-20C", "handling_requirements": "cold_chain"},
    {"sku_id": "COVERSLIP_24", "name": "Coverslip box", "vendor_id": "vendor_glassco", "unit": "box",
     "base_price_usd": 18, "tier_min_qty": "", "tier_price_usd": "", "shipping_per_order_usd": 12,
     "lead_business_days": 2, "storage": "ambient", "handling_requirements": ""},  # assumption
    {"sku_id": "PBS_1L", "name": "PBS buffer 1L", "vendor_id": "vendor_labbasics", "unit": "bottle",
     "base_price_usd": 14, "tier_min_qty": "", "tier_price_usd": "", "shipping_per_order_usd": 15,
     "lead_business_days": 3, "storage": "ambient", "handling_requirements": ""},  # assumption
    {"sku_id": "TIPS_200", "name": "Pipette tips 200uL", "vendor_id": "vendor_labbasics", "unit": "rack_pack",
     "base_price_usd": 42, "tier_min_qty": 10, "tier_price_usd": 38, "shipping_per_order_usd": 15,
     "lead_business_days": 3, "storage": "ambient", "handling_requirements": ""},  # assumption
    {"sku_id": "TUBES_15", "name": "15ml tubes", "vendor_id": "vendor_labbasics", "unit": "case",
     "base_price_usd": 55, "tier_min_qty": 6, "tier_price_usd": 50, "shipping_per_order_usd": 15,
     "lead_business_days": 3, "storage": "ambient", "handling_requirements": ""},  # assumption
    {"sku_id": "DAPI_1ML", "name": "DAPI stain 1ml", "vendor_id": "vendor_bioreagent", "unit": "vial",
     "base_price_usd": 85, "tier_min_qty": 3, "tier_price_usd": 78, "shipping_per_order_usd": 20,
     "lead_business_days": 2, "storage": "refrigerated_4C", "handling_requirements": "light_sensitive;hazard_review"},  # assumption
    {"sku_id": "DNA_KIT", "name": "DNA isolation kit", "vendor_id": "vendor_bioreagent", "unit": "kit",
     "base_price_usd": 310, "tier_min_qty": "", "tier_price_usd": "", "shipping_per_order_usd": 20,
     "lead_business_days": 4, "storage": "ambient", "handling_requirements": ""},  # assumption
    {"sku_id": "PCR_PLATES", "name": "PCR plate box", "vendor_id": "vendor_labbasics", "unit": "box",
     "base_price_usd": 64, "tier_min_qty": "", "tier_price_usd": "", "shipping_per_order_usd": 15,
     "lead_business_days": 3, "storage": "ambient", "handling_requirements": ""},  # assumption
]

# Lab stock. Moreno has no anti-GFP and no coverslips, so the plan must order them.
STOCK = [
    {"stock_id": "stk_moreno_antigfp", "lab_id": "lab_moreno", "sku_id": "ANTI_GFP_100", "quantity": 0, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_moreno_coverslip", "lab_id": "lab_moreno", "sku_id": "COVERSLIP_24", "quantity": 0, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_moreno_pbs", "lab_id": "lab_moreno", "sku_id": "PBS_1L", "quantity": 4, "expiry_date": "2027-06-30", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_patel_antigfp", "lab_id": "lab_patel", "sku_id": "ANTI_GFP_100", "quantity": 0, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_patel_tips", "lab_id": "lab_patel", "sku_id": "TIPS_200", "quantity": 6, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_chen_coverslip", "lab_id": "lab_chen", "sku_id": "COVERSLIP_24", "quantity": 3, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_chen_dapi", "lab_id": "lab_chen", "sku_id": "DAPI_1ML", "quantity": 1, "expiry_date": "2027-01-31", "ownership_source": "grant_purchase"},
    {"stock_id": "stk_rivera_pbs", "lab_id": "lab_rivera", "sku_id": "PBS_1L", "quantity": 8, "expiry_date": "2027-03-31", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_rivera_tubes", "lab_id": "lab_rivera", "sku_id": "TUBES_15", "quantity": 2, "expiry_date": "", "ownership_source": "lab_purchase"},
    {"stock_id": "stk_rivera_plates", "lab_id": "lab_rivera", "sku_id": "PCR_PLATES", "quantity": 1, "expiry_date": "", "ownership_source": "lab_purchase"},
]

# One non-confocal instrument is down Thursday morning of the demo week.  # assumption: which instrument
MAINTENANCE_WINDOWS = [
    {"maintenance_id": "mw_plate_reader_1", "resource_id": "plate_reader_1",
     "start_local": "2026-11-05T09:00:00-06:00", "end_local": "2026-11-05T13:00:00-06:00", "reason": "Annual calibration (synthetic)"},
]

# Coarse planning signal only, never spending authorization. Restricted visibility.
FUNDING_HINTS = [
    {"funding_hint_id": "fh_rivera_award_end", "lab_id": "lab_rivera", "category": "end_of_award",
     "milestone_date": "2026-12-15", "restricted_flag": True,
     "note": "Synthetic planning signal only; not a real grant record"},  # assumption: which lab and date
]

# Policy records (added at the team's request; values are the demo heuristics in docs/09-ALGORITHMS.md).
POLICIES = [
    {"policy_id": "pol_score_preferred_window", "key": "score.weight.meets_preferred_window", "value": 50, "unit": "points",
     "source": "docs/09 A soft objectives"},
    {"policy_id": "pol_score_hours_late", "key": "score.weight.hours_late", "value": -2, "unit": "points_per_hour", "source": "docs/09 A"},
    {"policy_id": "pol_score_room_switch", "key": "score.weight.room_switch_count", "value": -3, "unit": "points_per_switch", "source": "docs/09 A"},
    {"policy_id": "pol_score_owner_move", "key": "score.weight.requires_owner_move", "value": -4, "unit": "points", "source": "docs/09 A"},
    {"policy_id": "pol_score_extra_cost", "key": "score.weight.extra_internal_cost_units", "value": -1, "unit": "points_per_unit", "source": "docs/09 A"},
    {"policy_id": "pol_slot_step", "key": "scheduling.slot_step_minutes", "value": 15, "unit": "minutes", "source": "docs/09 A implementation"},
    {"policy_id": "pol_max_options", "key": "scheduling.max_options", "value": 3, "unit": "count", "source": "docs/09 A implementation"},
    # assumption: owner-move offers land on half-hour marks (gives the docs' 13:30-15:30 shift)
    {"policy_id": "pol_move_step", "key": "scheduling.move_step_minutes", "value": 30, "unit": "minutes", "source": "assumption"},
    {"policy_id": "pol_prep_transition", "key": "scheduling.prep_transition_minutes", "value": 15, "unit": "minutes",
     "source": "docs/00 prep 09:00-09:45 before imaging 10:00"},
    {"policy_id": "pol_overload", "key": "utilization.overload_threshold", "value": 0.85, "unit": "ratio", "source": "assumption"},
    {"policy_id": "pol_pool_window", "key": "pooling.window_days", "value": 7, "unit": "days", "source": "docs/02 M2.1"},
    {"policy_id": "pol_underuse_threshold", "key": "underuse.utilization_threshold", "value": 0.25, "unit": "ratio", "source": "docs/09 E"},
    {"policy_id": "pol_underuse_weeks", "key": "underuse.min_low_weeks_of_6", "value": 4, "unit": "weeks", "source": "docs/09 E"},
    {"policy_id": "pol_ewma_alpha", "key": "forecast.ewma_alpha", "value": 0.35, "unit": "ratio", "source": "docs/09 F"},
]

for _table in (STOCK, MAINTENANCE_WINDOWS, FUNDING_HINTS, POLICIES):
    for _row in _table:
        _row["provenance"] = PROVENANCE
