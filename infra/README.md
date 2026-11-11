# Infrastructure

Two CloudFormation stacks in account `767105089665`, region `us-east-1`.

| stack | folder | what | deployed by |
|---|---|---|---|
| `molpecer-portfolio` | `infra/portfolio/` | the portfolio bucket, its policy, the CloudFront distribution and its functions | the repo, on push to `main` |
| `molpecer-ci` | `infra/ci/` | the GitHub OIDC provider and the roles GitHub Actions assumes | you, by hand |

Outside both stacks, managed in the console: the ACM certificate (`*.molpecer.es`), the Route 53 zone and records, the registrar.

## How a change reaches production

Every path ends in a push to `main`: a direct push, a merged pull request, or a branch merged locally and pushed. No other branch deploys anything; the Environments `portfolio` and `portfolio-infra` only accept `main`.

- **Content** (`portfolio/**`): `.github/workflows/portfolio.yml` syncs the folder to the bucket and invalidates the cache. Nothing to preview, so it does not run on pull requests.
- **Portfolio infra** (`infra/portfolio/**`): `.github/workflows/portfolio-infra.yml`. On a pull request it lints and prints the change set in the job summary using a role that cannot execute. On `main` it lints, plans again, refuses any change set that would replace a resource, and executes the rest.
- **CI infra** (`infra/ci/**`): lint runs on pull requests, deploy is by hand. See below.

## The CI stack is deployed by hand

The CI stack defines what the workflows are allowed to do. A workflow able to deploy it could grant itself anything, so no role has that power. It changes only when a workflow needs a new permission, typically when the portfolio template gains a new resource type.

Preview, applies nothing:

    aws cloudformation deploy --profile personal --region us-east-1 --stack-name molpecer-ci --template-file infra/ci/template.yaml --capabilities CAPABILITY_NAMED_IAM --no-execute-changeset

Deploy:

    aws cloudformation deploy --profile personal --region us-east-1 --stack-name molpecer-ci --template-file infra/ci/template.yaml --capabilities CAPABILITY_NAMED_IAM

Order matters when a pull request needs both: deploy the CI stack first, then merge the pull request, otherwise the apply fails on a missing permission and rolls back.

Termination protection, once per stack:

    aws cloudformation update-termination-protection --profile personal --region us-east-1 --enable-termination-protection --stack-name molpecer-portfolio
    aws cloudformation update-termination-protection --profile personal --region us-east-1 --enable-termination-protection --stack-name molpecer-ci

## Roles, as deployed

| role | assumed by | can |
|---|---|---|
| `molpecer-portfolio-deploy` | `portfolio.yml`, Environment `portfolio` | read, write, delete objects in `molpecer.es`; invalidate the one distribution |
| `molpecer-portfolio-infra-plan` | `portfolio-infra.yml`, pull requests and `main` | create, read, delete change sets on `molpecer-portfolio` |
| `molpecer-portfolio-infra` | `portfolio-infra.yml`, Environment `portfolio-infra` | execute change sets on `molpecer-portfolio`; update the one distribution and its `molpecer-portfolio-*` functions; change settings of the one bucket |

GitHub holds no AWS secrets. The three role ARNs are Actions variables: `AWS_ROLE_ARN` on each Environment, `AWS_PLAN_ROLE_ARN` on the repository.

## Day to day

| want | do |
|---|---|
| change the site | edit `portfolio/`, push to `main` |
| change CloudFront or the bucket | edit `infra/portfolio/template.yaml`, open a pull request, read the plan, merge |
| give a workflow a new permission | edit `infra/ci/template.yaml`, deploy it by hand (above), then merge |
| see what the stack looks like | `aws cloudformation describe-stacks --profile personal --region us-east-1 --stack-name molpecer-portfolio` |
