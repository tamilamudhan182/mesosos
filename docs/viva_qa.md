# Mesh-SOS viva Q&A

**Q: What is a DTN?** A network where an end-to-end path may never exist at one time. Nodes use *store-carry-forward*: keep the message, physically carry it, forward on contact.

**Q: Why not just use normal routing (AODV/OLSR)?** They need a currently connected path. In a flood the network is partitioned most of the time.

**Q: Which layer does your project work at?** Application-layer overlay over UDP (discovery broadcast) and TCP (reliable exchange) on IP/Wi-Fi. Routing decisions are overlay routing.

**Q: How does discovery work?** Every 2 s each node broadcasts a small JSON beacon (name, TCP port, battery, gateway flag) to 255.255.255.255 on UDP ports 47000–47009. Receivers add the sender to the peer table; peers unseen for 10 s are considered gone.

**Q: What happens in one encounter?** Anti-entropy with a summary vector: both sides exchange HELLO = {list of message ids, ack list, battery, delivery-predictability table}. Each side then sends only messages the other lacks and that the routing rule allows, highest priority first.

**Q: Explain PriorityAware-DTN.** (1) Priority order: SOS > ACK > INFO, then urgency. (2) Copy budget L = base(type) × urgency factor × battery factor (SOS 16, INFO 4). (3) Weighted spray: copies split in proportion to each node's PRoPHET delivery predictability to a gateway. (4) Battery: peers <15% refuse INFO, <5% refuse everything. (5) With one copy left, hand over only to a clearly better carrier (SOS keeps an insurance copy). (6) ACKs from the gateway spread and purge delivered copies. (7) Buffer full → drop lowest priority, not oldest.

**Q: PRoPHET formula?** On meeting b: P(a,b) = P_old + (1−P_old)·P_init (0.75). Aging: P = P·γ^k (γ=0.98). Transitivity: P(a,c) = max(P_old, P_old + (1−P_old)·P(a,b)·P(b,c)·β) (β=0.25).

**Q: Results?** PriorityAware gets 93–100% SOS delivery with 2–5× fewer transmissions than Epidemic. Trade-off: INFO delivery drops (63–81%), and in dense networks (100–200 nodes) Epidemic/PRoPHET still deliver SOS equally or slightly better and faster — but at much higher overhead and battery cost. Its biggest win is the sparse 50-node case (93–96% SOS vs 70–87% Epidemic).

**Q: Why does Epidemic lose in sparse networks?** Finite buffers and short contacts: flooding fills buffers with everything and SOS gets dropped/crowded out.

**Q: Security?** Ed25519 signatures over all fields except the hop list; tampered or forged messages are rejected at nodes and the dashboard. Limitation: no PKI, so a new attacker key can still send spam SOS — future: rate limit per key, reputation.

**Q: How does the dashboard dedup?** By message id (multiple gateways can upload the same copy), then by (origin, normalised text) for repeated sends. Ranking score = 10·urgency + people (≤20) + waiting time (≤10).

**Q: Why SQLite?** Messages must survive app crash / phone reboot — that's the "store" in store-carry-forward.

**Q: Is this tested in reality?** Local multi-process demo (4 nodes, 3 hops, partition + recovery) passes automatically. Multi-device test procedure is in README — report what you measured.

**Q: Related work?** FireChat (shut down 2018), Bridgefy (BLE mesh, published security flaws), Briar (secure messenger, not SOS-prioritised), Serval (mesh phones, needs rooted phones/hardware), Meshtastic (LoRa hardware needed). None does urgency+battery-aware routing with a rescue-side triage dashboard on zero hardware.

**Q: Future work?** Android app with Wi-Fi Direct/BLE (no hotspot needed), LoRa relays, real mobility traces, PKI via pre-registered rescue keys, compression of summary vectors with Bloom filters.
