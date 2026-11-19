from Agent import Agent
from coalition_travel.domain.traveler_profile import CompatibilityResult
from Leader import CoalitionLeaderAgent
from Message import Message


class BrokerAgent(Agent):
    """
    Agent facilitateur (Directory Facilitator).
    Implémente l'algorithme de "Couplage" en regroupant les agents par destination.
    """

    def __init__(
        self,
        name,
        coalition_size=3,
        negotiate_on_formation=True,
        discounts=None,
        group_min_fare=400,
        group_release_date="01-Dec",
    ):
        super().__init__(name)
        if coalition_size < 2:
            raise ValueError("coalition_size must be at least 2")
        self.coalition_size = coalition_size
        self.negotiate_on_formation = negotiate_on_formation
        self.discounts = discounts or {2: 0.05, 3: 0.10, 4: 0.20}
        if any(size < 1 or not 0 <= rate < 1 for size, rate in self.discounts.items()):
            raise ValueError("discounts must map coalition sizes to rates in [0, 1)")
        if group_min_fare <= 0:
            raise ValueError("group_min_fare must be positive")
        self.group_min_fare = group_min_fare
        self.group_release_date = group_release_date
        self.formation_history = []
        self._seen_subscriptions = set()
        self.cohort_subscriptions = {}
        self.cohort_decisions = {}
        self.processed_cohorts = set()
        self.compatibility_history = []
        self.candidate_history = []
        # Dictionnaire pour stocker les listes d'attente : {"Tokyo": [agent1, agent2...]}
        self.subscriptions = {}

    def receive_message(self, message):
        if message.type == "SUBSCRIBE":
            if not isinstance(message.content, dict):
                raise ValueError("SUBSCRIBE content must be a mapping")
            destination = message.content.get("destination")
            if not isinstance(destination, str) or not destination.strip():
                raise ValueError("SUBSCRIBE requires a non-empty destination")
            destination = destination.strip()
            buyer = message.sender
            request_id = message.content.get("request_id")
            if request_id is not None:
                self._receive_cohort_subscription(message, destination, buyer, request_id)
                return
            subscription_key = (destination, buyer.name)
            if subscription_key in self._seen_subscriptions:
                return
            self._seen_subscriptions.add(subscription_key)

            # Ajouter l'agent à la liste d'attente pour cette destination
            if destination not in self.subscriptions:
                self.subscriptions[destination] = []
            self.subscriptions[destination].append(buyer)

            print(
                f"[{self.name}] NOUVELLE INSCRIPTION : {buyer.name} veut aller à {destination}. "
                f"(Total en attente: {len(self.subscriptions[destination])})"
            )

            # Vérifier si le seuil configuré est atteint.
            self.check_for_coalition(destination)

    def _receive_cohort_subscription(self, message, destination, buyer, request_id):
        """Keep explicitly grouped request profiles isolated from other requests."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        content = message.content
        expected = content.get("cohort_size")
        decision = content.get("compatibility")
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise TypeError("cohort_size must be an integer")
        if expected < 1:
            raise ValueError("cohort_size must be a positive integer")
        if not isinstance(decision, CompatibilityResult):
            raise TypeError("compatibility must be an application-validated CompatibilityResult")
        key = (destination, request_id)
        if key in self.processed_cohorts:
            return
        members = self.cohort_subscriptions.setdefault(key, [])
        if any(member.name == buyer.name for member in members):
            return
        members.append(buyer)
        decisions = self.cohort_decisions.setdefault(key, [])
        decisions.append(decision)
        if len(members) < expected:
            return
        if len(members) != expected:
            raise ValueError("received more cohort profiles than declared")
        if any(candidate != decision for candidate in decisions):
            raise ValueError("cohort members must carry the same compatibility decision")
        if set(decision.profile_ids) != {member.name for member in members}:
            raise ValueError("compatibility profile IDs must match cohort buyer IDs")
        status = decision.status
        record = {
            "request_id": request_id,
            "destination": destination,
            "status": status,
            "members": tuple(members),
            "reasons": decision.reasons,
            "knowledge_sources": decision.knowledge_sources,
        }
        self.compatibility_history.append(record)
        if status != "incompatible":
            self.candidate_history.append(record)
        if status == "compatible" and "common_offer_satisfies_all_profiles" in decision.reasons:
            self.form_coalition(
                members[:], destination, self.discounts.get(len(members), 0.0), negotiate=False
            )
        del self.cohort_subscriptions[key]
        del self.cohort_decisions[key]
        self.processed_cohorts.add(key)

    def check_for_coalition(self, destination):
        group = self.subscriptions[destination]

        discount = self.discounts.get(self.coalition_size, 0.0)
        if len(group) == self.coalition_size:
            print(
                f"\n[{self.name}] COALITION FORMÉE ({self.coalition_size} membres) pour {destination} !"
            )
            self.form_coalition(group, destination, discount=discount)
            self.subscriptions[destination] = []  # Vider la liste

    def form_coalition(self, members, destination, discount, negotiate=None):
        """Crée dynamiquement une entité pour représenter le groupe."""
        leader_name = f"Coalition_{destination}_({len(members)}_membres)"
        self.formation_history.append((destination, tuple(members), discount))

        # Avertir les membres
        for member in members:
            msg = Message(
                self, member, "INFORM", f"Coalition formée avec {discount * 100}% de réduction!"
            )
            member.receive_message(msg)

        # ÉTAPE 2 — le broker délègue la négociation à un CoalitionLeaderAgent
        print(
            f"\n  ÉTAPE 2 — Broker crée CoalitionLeaderAgent '{leader_name}' et délègue la négociation."
        )
        should_negotiate = self.negotiate_on_formation if negotiate is None else negotiate
        if should_negotiate:
            leader = CoalitionLeaderAgent(
                leader_name,
                members,
                discount,
                group_min_fare=self.group_min_fare,
                group_release_date=self.group_release_date,
            )
            leader.negotiate_for_group()

    def finalize_pending(self, destination, min_size=2):
        """Form one final smaller coalition from buyers still waiting."""
        if min_size < 2:
            raise ValueError("min_size must be at least 2")
        group = self.subscriptions.get(destination, [])
        if len(group) < min_size:
            return None
        discount = self.discounts.get(len(group), 0.0)
        self.form_coalition(group[:], destination, discount)
        self.subscriptions[destination] = []
        return group[:]
