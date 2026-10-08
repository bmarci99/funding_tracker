# Sources checked and rejected

Scouts: skip these unless the reason has obviously changed. Format: `source — reason (date checked)`.

## 2026-10-08 pass
**Need a local entity we don't have**
- FFG Austria, aws, WWTF, Wirtschaftsagentur Wien — AT entity needed
- Danish funders (Nordea-fonden, TrygFonden, Egmont, Industriens Fond, Sundhedsstyrelsen) — DK entity / rolling only
- WASP / Wallenberg AI — SE only
- Forces in Mind Trust, AWS Imagine, NIA, NASA TRISH / TechLeap, ACL — UK or US only
- Bayerische TF-Stiftung, BayDiGuP, IBB Berlin, BW Innovationsgutscheine — regional entity only, or rolling with no call index

**Blocked, or no call index**
- Danmarks Innovationsfond — WAF proof-of-work (HTTP 454). Don't try to defeat it; watch Grand Solutions manually.
- ESA OSIP (ideas.esa.int) — login wall
- FundingBox, F6S — JS shells; F6S returns 405. Cascade Funding Hub RSS covers them.
- Templeton World Charity — no index, no unsolicited proposals
- LEGO Foundation, Werner Siemens, Dieter Schwarz, Wellcome Leap — invitation-only or no call index
- DSEE Förderdatenbank — JS SPA, low fit
- ZIM, DATIpilot — rolling or closed, not trackable as a feed

**Off-profile**
- Deutsche Krebshilfe, Kræftens Bekæmpelse, Wilhelm Sander, KWF, José Carreras, CRUK, ZonMw, EKFS — academic or clinical research only
- Aktion Mensch — disability inclusion, gemeinnützig applicants only (low fit; revisit once the DE gGmbH exists)
- Cyberagentur, NATO SPS — defence
- XPRIZE, HeroX, Challenge Works — off-theme or US-only prizes
- AAL Programme — wound down
- NGI — programme over
- Opportunity Desk, fundsforNGOs, fundsforcompanies, eufundingportal.eu blog — aggregator noise
- EEA/Norway HU Civil Society Fund — democracy and human-rights themes only
- Velux Stiftung (CH), VELUX FONDEN (DK) — no tech fit
- PtJ Förderinitiativen — energy and bio heavy
- Förderdatenbank des Bundes RSS — regional business programmes, fit 0 even with a title filter
- Gips-Schüle-Stiftung — nomination-only prize, generic titles
- Interreg Baltic Sea, North Sea, Alpine Space, HU-SK, AT-CZ, SK-AT — closed, or capitalisation-only for existing partners

**Leads to re-check later**
- Interreg Slovenia–Hungary continuous call (aggregator claim, unverified)
- foerderinfo.bund.de RSS (timed out from here; retry)
- EU Cluster Collaboration Platform robotics RSS (needs leading-junk strip before XML parse)
- Hungarian space office (ESA RPA / HUR): no 2026 call seen; ask the Hungarian space department
- ESA BIC Hungary / Hessen / Austria: single rolling pages, next window spring 2027
