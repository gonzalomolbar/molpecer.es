# Infrastructure

Three CloudFormation stacks in account `767105089665`, region `us-east-1`: one that enables the pipelines, one for the domain, one for the portfolio.

| stack | folder | what | deployed by |
|---|---|---|---|
| `molpecer-domain` | `infra/domain/` | the `molpecer.es` hosted zone and what belongs to the domain rather than a site: the mail identity with DKIM, SPF, DMARC, null MX | the repo, on push to `main` (zone imported by hand once) |
| `molpecer-portfolio` | `infra/portfolio/` | the portfolio certificate, the bucket, its policy, the CloudFront distribution with its www-redirect function, the A and AAAA records for the apex and www | the repo, on push to `main` |
| `molpecer-ci` | `infra/ci/` | the GitHub OIDC provider and every role the workflows assume | you, by hand |

Outside the stacks: the domain registration (Route 53 Registrar), the certificate validation CNAME that ACM writes into the zone (not a stack resource; it must stay for renewals), the account-level billing alarm with its `NotifyMe` topic, and the `monthly-10usd` budget. The zone's NS and SOA records come with the zone.

## How a change reaches production

Every path ends in a push to `main`: a direct push, a merged pull request, or a branch merged locally and pushed. No other branch deploys anything; every Environment only accepts `main`.

- **Content** (`portfolio/**`): `.github/workflows/portfolio.yml` syncs the folder to the bucket and invalidates the cache. Nothing to preview, so it does not run on pull requests.
- **Domain** (`infra/domain/**`): `.github/workflows/domain-infra.yml`, same shape as the portfolio infra workflow: plan on pull requests with a read-only role, apply on `main` refusing a change set that would replace the zone or the mail identity.
- **Portfolio infra** (`infra/portfolio/**`): `.github/workflows/portfolio-infra.yml`. On a pull request it lints and prints the change set in the job summary using a role that cannot execute. On `main` it lints, plans again, refuses a change set that would replace the bucket or the distribution, executes, and turns on termination protection. Everything in that stack was created by it except the zone, which lives in `molpecer-dns`.
- **CI infra** (`infra/ci/**`): lint runs on pull requests, deploy is by hand. See below.

## The CI stack is deployed by hand

The CI stack defines what the workflows are allowed to do. A workflow able to deploy it could grant itself anything, so no role has that power. It changes only when a workflow needs a new permission, typically when a feature template gains a new resource type. Add `--no-execute-changeset` to preview first.

    aws cloudformation deploy --profile personal --region us-east-1 --stack-name molpecer-ci --template-file infra/ci/template.yaml --capabilities CAPABILITY_NAMED_IAM

Order matters when a pull request needs both: deploy the CI stack first, then merge the pull request, otherwise the apply fails on a missing permission and rolls back.

The domain stack was born by importing the zone (the zone predates every stack; an import change set may contain nothing but the imported resource, so a zone-only copy of the template was used), and the workflow has managed it since.

Termination protection: the workflows turn it on for their stacks after every apply; the CI stack gets it once by hand:

    aws cloudformation update-termination-protection --profile personal --region us-east-1 --enable-termination-protection --stack-name molpecer-ci

## Roles, as deployed

| role | assumed by | can |
|---|---|---|
| `molpecer-domain-infra-plan` | `domain-infra.yml`, pull requests and `main` | create, read, delete change sets on `molpecer-domain` |
| `molpecer-domain-infra` | `domain-infra.yml`, Environment `domain-infra` | execute change sets on `molpecer-domain`; zone settings; only the apex TXT and MX, `_dmarc` and DKIM records; the `molpecer.es` mail identity; denied zone creation and deletion |
| `molpecer-portfolio-deploy` | `portfolio.yml`, Environment `portfolio` | read, write, delete objects in `molpecer.es`; invalidate the one distribution |
| `molpecer-portfolio-infra-plan` | `portfolio-infra.yml`, pull requests and `main` | create, read, delete change sets on `molpecer-portfolio` |
| `molpecer-portfolio-infra` | `portfolio-infra.yml`, Environment `portfolio-infra` | execute change sets on `molpecer-portfolio`; update the one distribution and its `molpecer-portfolio-*` functions; change settings of the one bucket; request certificates; write only `molpecer.es`, `www.molpecer.es` and validation records in the zone; denied zone creation and deletion |

GitHub holds no AWS secrets. Actions variables: `AWS_ROLE_ARN` on each of the three Environments (`domain-infra`, `portfolio`, `portfolio-infra`, all restricted to `main`); on the repository `DOMAIN_PLAN_ROLE_ARN` and `AWS_PLAN_ROLE_ARN`.

## Day to day

| want | do |
|---|---|
| change a domain-level record or the mail identity | edit `infra/domain/template.yaml`, open a pull request, read the plan, merge |
| change the site | edit `portfolio/`, push to `main` |
| change CloudFront or the bucket | edit `infra/portfolio/template.yaml`, open a pull request, read the plan, merge |
| give a workflow a new permission | edit `infra/ci/template.yaml`, deploy it by hand (above), then merge |
| see what the stack looks like | `aws cloudformation describe-stacks --profile personal --region us-east-1 --stack-name molpecer-portfolio` |
