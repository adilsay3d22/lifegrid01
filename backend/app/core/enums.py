"""Enumerations from spec section 11, shared by models (DB enum types) and schemas."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class SiteType(StrEnum):
    hospital = "hospital"
    blood_bank = "blood_bank"


class Role(StrEnum):
    bank_manager = "bank_manager"
    hospital_lead = "hospital_lead"
    donor_coordinator = "donor_coordinator"
    donor = "donor"
    requester = "requester"
    admin = "admin"
    auditor = "auditor"


STAFF_ROLES = {Role.bank_manager, Role.hospital_lead, Role.donor_coordinator, Role.admin, Role.auditor}


class Abo(StrEnum):
    O = "O"  # noqa: E741
    A = "A"
    B = "B"
    AB = "AB"


class Rh(StrEnum):
    pos = "pos"
    neg = "neg"


class Component(StrEnum):
    red_cells = "red_cells"
    platelets = "platelets"
    plasma = "plasma"


class UnitStatus(StrEnum):
    available = "available"
    reserved = "reserved"
    in_transit = "in_transit"
    quarantined = "quarantined"
    issued = "issued"
    expired = "expired"
    discarded = "discarded"


def db_enum(e: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(e, name=name, values_callable=lambda x: [m.value for m in x], native_enum=True, validate_strings=True)


GROUPS: list[tuple[Abo, Rh]] = [(a, r) for a in Abo for r in Rh]


class Urgency(StrEnum):
    emergency = "emergency"
    urgent = "urgent"
    routine = "routine"


class RequestStatus(StrEnum):
    submitted = "submitted"
    confirmed = "confirmed"
    covered_by_stock = "covered_by_stock"
    matching = "matching"
    fulfilled = "fulfilled"
    partially_fulfilled = "partially_fulfilled"
    unfilled = "unfilled"
    cancelled = "cancelled"


OPEN_REQUEST = {RequestStatus.submitted, RequestStatus.confirmed, RequestStatus.covered_by_stock, RequestStatus.matching}


class MatchStatus(StrEnum):
    invited = "invited"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    donated = "donated"
    no_show = "no_show"
    deferred_on_site = "deferred_on_site"
    withdrawn = "withdrawn"


ACCEPTED_LIKE = {MatchStatus.accepted, MatchStatus.donated, MatchStatus.no_show, MatchStatus.deferred_on_site, MatchStatus.withdrawn}


class Availability(StrEnum):
    available = "available"
    unavailable = "unavailable"
    travelling = "travelling"
