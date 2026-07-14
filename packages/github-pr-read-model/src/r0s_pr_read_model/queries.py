REPOSITORIES = """
query Repositories($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor, isArchived: false,
      orderBy: {field: NAME, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner isArchived }
    }
  }
}
"""

PULL_REQUESTS = """
query PullRequests($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 100, after: $cursor, states: OPEN,
      orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url isDraft author { login } baseRefName headRefName headRefOid
        reviewDecision mergeable mergeStateStatus
        commits(last: 1) { nodes { commit { oid statusCheckRollup {
          contexts(first: 100) { pageInfo { hasNextPage endCursor } nodes {
            __typename
            ... on CheckRun { name status conclusion detailsUrl
              checkSuite { app { databaseId slug } } }
            ... on StatusContext { context state targetUrl }
          } }
        } } } }
      }
    }
  }
}
"""

MORE_CONTEXTS = """
query MoreContexts($owner: String!, $name: String!, $oid: GitObjectID!, $cursor: String!) {
  repository(owner: $owner, name: $name) {
    object(oid: $oid) { ... on Commit { statusCheckRollup { contexts(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor } nodes {
        __typename
        ... on CheckRun { name status conclusion detailsUrl checkSuite { app { databaseId slug } } }
        ... on StatusContext { context state targetUrl }
      }
    } } } }
  }
}
"""

BRANCH_PROTECTION = """
query BranchProtection($owner: String!, $name: String!, $qualifiedName: String!) {
  repository(owner: $owner, name: $name) {
    ref(qualifiedName: $qualifiedName) {
      branchProtectionRule {
        pattern requiresStatusChecks requiresStrictStatusChecks
        requiredStatusChecks { context app { databaseId slug } }
      }
    }
  }
}
"""
