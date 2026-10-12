# Guided questions

Ask one topic at a time. Offer defaults; never assume direction, site or severity without asking.

1. **Site.** "Which site is this for? (I'll list the paired sites.)" Then: "What does the customer call it?"
2. **Input.** "Would you like a spreadsheet to fill in, to answer questions here, or to paste a list?"
3. **Zones.** "List your zones, e.g. Enterprise, DMZ, Control, Safety. For each, optionally: a one-line description, Purdue level (0-5), target security level (1-4), criticality."
4. **Address space.** For each zone: "What address space belongs to <zone>? A CIDR such as 10.10.1.0/24 is best because assets that appear later join automatically. I can also take an address range, a list of IPs, a VLAN, or specific assets you pick." Repeat until the user says that zone is complete.
5. **Conduits.** "Which zones are allowed to talk? For each pair: who starts the conversation (A to B, B to A, or both really initiate), and which protocols are allowed?" If they say "both ways" ask once whether both sides genuinely initiate, because direction is enforced.
6. **Options.**
   - "Create sample asset groups (PLCs, HMIs, ...)?" default no
   - "Create sample policies (remote admin to controllers, new asset in a zone)?" default no
   - "Create policies enabled or disabled?" default **disabled**, recommended for a first run
   - "Severity for the policies?" default medium
   - "Name prefix for everything I create?" default `IEC62443`
   - Only if asked about noise: "treat conduits as two-way for boundary checks (direction tolerant)?" default no
7. **Confirm** the validated model back in a short table before planning.
