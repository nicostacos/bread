# Hosting options for Bread Bot

Reviewed 2026-11-04. Requirement: free or a trial of at least two weeks. The user has an approved GitHub Student Developer Pack. No infrastructure has been provisioned.

## Recommendation

Heroku Basic: one 512 MB worker at USD 7/month, covered by the GitHub student allowance of USD 13/month for 24 months if total eligible account usage remains within the allowance. Requires a payment card; overages are billed. Credits must be redeemed and confirmed in the account dashboard before provisioning.

Run a worker-only app with one replica. Keep Supabase as the database, use platform secrets and logs, and support graceful restarts. No public web service or persistent disk is needed for the bot itself. Hosting choice is a recommendation pending user selection.

Sources:
- https://education.github.com/pack
- https://www.heroku.com/github-students/
- https://www.heroku.com/pricing/
- https://help.heroku.com/Z3RHNRHD/how-does-the-heroku-for-github-students-program-work
- https://devcenter.heroku.com/articles/eco-dyno-hours

## Alternatives

- Azure for Students: USD 100 credit valid for 12 months, eligible students may renew annually; no payment card required. A Linux VM can run the bot continuously but requires OS/process maintenance. Age and academic eligibility apply; verify available free VM sizes and disk/network charges. https://learn.microsoft.com/azure/education-hub/about-azure-for-students and https://azure.microsoft.com/en-us/free/students/
- Oracle Always Free: ongoing eligible VM resources with card verification, subject to regional capacity and idle-instance reclamation. More administration and availability uncertainty than Heroku. Verify current free allocations during signup rather than relying on older 4-core/24GB guides. https://www.oracle.com/cloud/free/ and https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Railway: USD 5 trial credit for up to 30 days, but credits can exhaust before 14 days; it does not guarantee the requested minimum free evaluation duration. https://docs.railway.com/pricing/free-trial

## Exclusions and changed offers

- Fly.io's seven-day trial does not meet the user's requirement.
- DigitalOcean's GitHub student offer ended in 2026; do not promise the old student credits. Official changelog: https://github.com/github-education-resources/Student-Developer-Pack-Current-Partners-FAQ/blob/main/SDP-changelog.md
- Render free web hosting sleeps without inbound traffic and has no free background worker. It is unsuitable for this continuously connected Discord bot. https://render.com/docs/free
- Static-site hosts and short-lived serverless functions cannot directly replace this Python Gateway process while preserving its current event and prefix-command behavior.

Heroku Eco is a possible lower-cost variant: worker-only Eco apps do not sleep, but adding a sleeping web dyno affects its workers. Basic remains the recommendation because student credit covers it and its operating model is straightforward.
