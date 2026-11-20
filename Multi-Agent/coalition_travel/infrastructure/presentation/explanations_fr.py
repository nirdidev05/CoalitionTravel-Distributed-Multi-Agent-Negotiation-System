"""Deterministic French messages for the 13 explanation codes (scope review §5, I3-B).

A message depends only on the code and its typed parameters: no clock, no locale, no
randomness. Amounts are formatted from integer cents ("3 801,00 €"); a rational amount
that is not a whole number of cents is shown rounded, with its exact value.

Vocabulary (plan §1.2): "proposition", "prix négocié (simulation)", "répartition
calculée", "demande validée". The words "meilleur", "optimal" and "avantageux" are never
applied to the situation of the person (scope review §5.4); no forbidden word is used.
"""

from fractions import Fraction

from coalition_travel.application.trip_proposal import (
    AloneNoBeneficialCoalitionParams,
    AloneSocialOptimumParams,
    BudgetCapActiveParams,
    CapacityModelViolatedParams,
    ComponentTooLargeParams,
    DirectPreferenceNotMetParams,
    Explanation,
    NoAdmissibleOfferParams,
    NoSoloReferenceParams,
    OfferRejectedParams,
    ProjectionActiveParams,
    ServedInCoalitionParams,
    ViolationView,
)

# --- amounts ------------------------------------------------------------------------------


def euros(cents: int) -> str:
    """Integer cents as French euros: 380100 -> "3 801,00 €"."""
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError("amounts are integer cents")
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", " ")
    return f"{sign}{grouped},{fraction:02d} €"


def euros_exact(value: Fraction) -> str:
    """A rational amount in cents; a non-integer value keeps its exact form."""
    value = Fraction(value)
    if value.denominator == 1:
        return euros(value.numerator)
    return (
        f"≈ {euros(round(value))} (valeur exacte : {value.numerator}/{value.denominator} centimes)"
    )


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


# --- request level ------------------------------------------------------------------------

FIELD_LABELS = {
    "destination": "la destination",
    "travellers": "le nombre de voyageurs",
    "budget_per_person": "le budget par personne",
}
CLARIFICATION_QUESTIONS = {
    "destination": "Quelle est la destination du voyage ?",
    "travellers": "Combien de personnes voyagent ?",
    "budget_per_person": "Quel est le budget par personne, en euros ?",
}


def needs_clarification_message(missing_fields) -> str:
    labels = [FIELD_LABELS[field] for field in missing_fields]
    return "Il manque des informations pour traiter la demande : " + ", ".join(labels) + "."


def unknown_place_message() -> str:
    return "Le lieu demandé n'est pas reconnu par le référentiel des lieux."


REQUEST_REJECTION_MESSAGES = {
    "budget_below_one_cent": "Le budget par personne est inférieur à un centime.",
    "budget_out_of_range": (
        "Le budget par personne dépasse le montant maximal pris en charge (1 000 000 000 €)."
    ),
    "budget_total_out_of_range": (
        "Le budget total de la demande dépasse le montant maximal pris en charge (1 000 000 000 €)."
    ),
}


def forbidden_term_message(path: str) -> str:
    """D-I3-17: names the field, never quotes the value."""
    return (
        f"Le champ {path} contient un terme qui ne peut pas figurer dans une proposition simulée."
    )


# --- offers -------------------------------------------------------------------------------

REASON_LABELS = {
    "destination_mismatch": "la destination de l'offre ne correspond pas à la demande",
    "offer_departs_before_reference_date": "l'offre part avant la date de référence",
    "departure_before_window": "le départ a lieu avant la date de départ demandée",
    "arrival_after_window": "l'arrivée a lieu après la date d'arrivée demandée",
    "direct_flight_required": "un vol direct est exigé et l'offre comporte une escale",
    "excluded_supplier": "le fournisseur de l'offre est exclu",
    "unit_exceeds_offer_capacity": "la demande compte plus de voyageurs que la capacité de l'offre",
}


def violation_text(violation: ViolationView) -> str:
    text = REASON_LABELS[violation.reason]
    if violation.profile_id is not None:
        text += f" (profil {violation.profile_id})"
    return text


# --- the eleven proposal codes ------------------------------------------------------------


def _served(params: ServedInCoalitionParams) -> str:
    others = _plural(params.other_requests, "autre demande", "autres demandes")
    return (
        f"Votre demande voyage avec {others} sur l'offre {params.offer_id}. "
        f"Économie calculée pour votre demande : {euros(params.saving_cents)}."
    )


def _alone_no_beneficial(params: AloneNoBeneficialCoalitionParams) -> str:
    alone = "Votre demande voyage seule, au prix négocié (simulation) de sa référence."
    if params.evaluated == 0:
        return (
            "Aucune autre demande ne partageait d'offre admissible avec la vôtre : aucune "
            f"coalition n'a été évaluée. {alone}"
        )
    evaluated = _plural(params.evaluated, "coalition évaluée", "coalitions évaluées")
    return (
        f"Parmi les {evaluated} par P4 qui incluaient votre demande (toutes celles qui "
        "partageaient une offre admissible avec elle), "
        f"{params.without_agreement} n'ont abouti à aucun accord et "
        f"{params.without_saving} n'ont dégagé aucune économie. {alone}"
    )


def _alone_social_optimum(params: AloneSocialOptimumParams) -> str:
    lines = [
        (
            "La répartition retenue maximise la valeur totale du groupe de demandes "
            f"({euros(params.component_value_cents)}). Elle n'inclut votre demande dans aucune "
            "coalition : votre demande voyage seule, au prix négocié (simulation) de sa "
            "référence. Parmi les coalitions évaluées qui incluaient votre demande, voici celles "
            "qui donnaient la plus grande valeur totale, avec l'écart par rapport à la "
            "répartition retenue :"
        )
    ]
    for alternative in params.alternatives:
        line = (
            f"- coalition de {alternative.size} demandes sur l'offre {alternative.offer_id} : "
            f"valeur créée {euros(alternative.value_cents)}, valeur totale possible "
            f"{euros(alternative.best_total_cents)}, "
        )
        if alternative.gap_cents == 0:
            line += (
                "même valeur totale que la répartition retenue ; celle-ci a été choisie par la "
                "règle de départage documentée de P4."
            )
        else:
            line += f"écart {euros(alternative.gap_cents)}."
        lines.append(line)
    lines.append(
        "Ce résultat découle de l'objectif collectif ; il ne signifie pas qu'une coalition "
        "aurait été défavorable à votre demande."
    )
    return "\n".join(lines)


def _no_admissible_offer(params: NoAdmissibleOfferParams) -> str:
    offers = _plural(params.rejected_offers, "offre a été écartée", "offres ont été écartées")
    return (
        "Aucune offre du catalogue ne correspond à votre demande : "
        f"{offers} par les règles d'admissibilité (détail par offre)."
    )


def _no_solo_reference(params: NoSoloReferenceParams) -> str:
    attempts = _plural(params.failed_attempts, "négociation", "négociations")
    return (
        f"Aucune négociation individuelle n'a abouti ({attempts} sans accord) : votre demande "
        "n'a pas de prix de référence et ne peut pas entrer dans une coalition."
    )


def _component_too_large(params: ComponentTooLargeParams) -> str:
    return (
        f"Le groupe de demandes compatibles compte {params.component_units} demandes, "
        f"au-delà de la limite de calcul de {params.max_component_units} : aucune "
        "répartition n'est calculée pour ce groupe."
    )


def _capacity_model_violated(params: CapacityModelViolatedParams) -> str:
    offers = ", ".join(params.offer_ids)
    return (
        "Les demandes compatibles dépassent la capacité de l'offre ou des offres "
        f"{offers} dans le modèle de capacité simplifié : aucune négociation n'a été lancée."
    )


def _projection_active(params: ProjectionActiveParams) -> str:
    text = (
        "Les contributions calculées ont été ajustées pour qu'aucun paiement ne soit négatif "
        "ni ne dépasse la référence (projection ; décalage commun "
        f"{euros_exact(params.lambda_star_cents)})."
    )
    if params.unit_saturated:
        text += " Pour votre demande, l'ajustement atteint une borne."
    return text


def _budget_cap_active(params: BudgetCapActiveParams) -> str:
    profiles = ", ".join(params.saturated_profile_ids)
    return (
        "Le paiement de votre demande est réparti en respectant le budget de chaque "
        f"voyageur ; le budget est atteint pour le ou les profils : {profiles}. Part égale "
        f"des autres voyageurs : {euros_exact(params.unit_tau_cents)}."
    )


def _offer_rejected(params: OfferRejectedParams) -> str:
    reasons = " ; ".join(violation_text(violation) for violation in params.violations)
    return f"Offre {params.offer_id} écartée : {reasons}."


def _direct_preference_not_met(params: DirectPreferenceNotMetParams) -> str:
    profiles = ", ".join(params.profile_ids)
    text = (
        f"La préférence pour un vol direct (profils : {profiles}) n'est pas satisfaite par "
        f"l'offre retenue {params.offer_id}, au prix catalogue de "
        f"{euros(params.retained_list_total_cents)} pour les places du bloc."
    )
    if params.best_direct is None:
        return text + " Aucune offre directe admissible ne pouvait accueillir ces places."
    return text + (
        f" L'offre directe admissible au plus bas prix catalogue était "
        f"{params.best_direct.offer_id}, à {euros(params.best_direct.list_total_cents)} "
        "pour le même nombre de places (information seulement)."
    )


_MESSAGES = {
    "served_in_coalition": _served,
    "alone_no_beneficial_coalition": _alone_no_beneficial,
    "alone_social_optimum": _alone_social_optimum,
    "no_admissible_offer": _no_admissible_offer,
    "no_solo_reference": _no_solo_reference,
    "component_too_large": _component_too_large,
    "capacity_model_violated": _capacity_model_violated,
    "projection_active": _projection_active,
    "budget_cap_active": _budget_cap_active,
    "offer_rejected": _offer_rejected,
    "direct_preference_not_met": _direct_preference_not_met,
}


def explanation_message(explanation: Explanation) -> str:
    """French message of one explanation of a proposal."""
    if type(explanation) is not Explanation:
        raise TypeError("explanation must be an Explanation")
    return _MESSAGES[explanation.code](explanation.params)
