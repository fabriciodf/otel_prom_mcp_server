# Bug Triage Automation Documentation

This document describes the automated bug triage system implemented for the Prometheus MCP Server repository using GitHub Actions.

## Overview

The automated triage system helps maintain issue quality, improve response times, and ensure consistent handling of bug reports and feature requests through intelligent automation.

## System Components

### 1. Automated Workflows

#### `bug-triage.yml` - Core Triage Automation
- **Triggers**: Issue events (opened, edited, labeled, unlabeled, assigned, unassigned), issue comments, scheduled runs (every 6 hours), manual dispatch
- **Functions**:
  - Auto-labels new issues based on content analysis
  - Assigns issues to maintainers based on component labels
  - Updates triage status when issues are assigned
  - Welcomes new contributors
  - Manages stale issues (marks stale after 30 days, closes after 7 additional days)
  - Links PRs to issues and updates status on PR merge

#### `issue-management.yml` - Advanced Issue Management
- **Triggers**: Issue events, comments, daily scheduled runs, manual dispatch
- **Functions**:
  - Enhanced auto-triage with pattern matching
  - Smart assignment based on content and labels
  - Issue health monitoring and escalation
  - Comment-based automated responses
  - Duplicate detection for new issues

#### `label-management.yml` - Label Consistency
- **Triggers**: Manual dispatch, weekly scheduled runs
- **Functions**:
  - Synchronizes label schema across the repository
  - Creates missing labels with proper colors and descriptions
  - Audits and reports on unused labels
  - Migrates deprecated labels to new schema

#### `triage-metrics.yml` - Reporting and Analytics
- **Triggers**: Daily and weekly scheduled runs, manual dispatch
- **Functions**:
  - Collects comprehensive triage metrics
  - Generates detailed markdown reports
  - Tracks response times and resolution rates
  - Monitors triage efficiency and quality
  - Creates weekly summary issues

### 2. Issue Templates

#### Bug Report Template (`bug_report.yml`)
Comprehensive template for bug reports including:
- Pre-submission checklist
- Priority level classification
- Detailed reproduction steps
- Environment information (OS, Python version, Prometheus version)
- Configuration and log collection
- Component classification

#### Feature Request Template (`feature_request.yml`)
Structured template for feature requests including:
- Feature type classification
- Problem statement and proposed solution
- Use cases and technical implementation ideas
- Breaking change assessment
- Success criteria and compatibility considerations

#### Question/Support Template (`question.yml`)
Template for questions and support requests including:
- Question type classification
- Experience level indication
- Current setup and attempted solutions
- Urgency level assessment

### 3. Label Schema

The system uses a hierarchical label structure:

#### Priority Labels
- `priority: critical` - Immediate attention required
- `priority: high` - Should be addressed soon
- `priority: medium` - Normal timeline
- `priority: low` - Can be addressed when convenient

#### Status Labels
- `status: needs-triage` - Issue needs initial triage
- `status: in-progress` - Actively being worked on
- `status: waiting-for-response` - Waiting for issue author
- `status: stale` - Marked as stale due to inactivity
- `status: in-review` - Has associated PR under review
- `status: blocked` - Blocked by external dependencies

#### Component Labels
- `component: prometheus` - Prometheus integration issues
- `component: mcp-server` - MCP server functionality
- `component: deployment` - Deployment and containerization
- `component: authentication` - Authentication mechanisms
- `component: configuration` - Configuration and setup
- `component: logging` - Logging and monitoring

#### Type Labels
- `type: bug` - Something isn't working as expected
- `type: feature` - New feature or enhancement
- `type: documentation` - Documentation improvements
- `type: performance` - Performance-related issues
- `type: testing` - Testing and QA related
- `type: maintenance` - Maintenance and technical debt

#### Environment Labels
- `env: windows` - Windows-specific issues
- `env: macos` - macOS-specific issues
- `env: linux` - Linux-specific issues
- `env: docker` - Docker deployment issues

#### Difficulty Labels
- `difficulty: beginner` - Good for newcomers
- `difficulty: intermediate` - Requires moderate experience
- `difficulty: advanced` - Requires deep codebase knowledge

## Automation Rules

### Auto-Labeling Rules

1. **Priority Detection**:
   - `critical`: Keywords like "critical", "crash", "data loss", "security"
   - `high`: Keywords like "urgent", "blocking"
   - `low`: Keywords like "minor", "cosmetic"
   - `medium`: Default for other issues

2. **Component Detection**:
   - `prometheus`: Keywords related to Prometheus, metrics, PromQL
   - `mcp-server`: Keywords related to MCP, server, transport
   - `deployment`: Keywords related to Docker, containers, deployment
   - `authentication`: Keywords related to auth, tokens, credentials

3. **Type Detection**:
   - `feature`: Keywords like "feature", "enhancement", "improvement"
   - `documentation`: Keywords related to docs, documentation
   - `performance`: Keywords like "performance", "slow"
   - `bug`: Default for issues not matching other types

### Assignment Rules

Issues are automatically assigned based on:
- Component labels (all components currently assign to @pab1it0)
- Priority levels (critical issues get immediate assignment with notification)
- Special handling for performance and authentication issues

### Stale Issue Management

1. Issues with no activity for 30 days are marked as `stale`
2. A comment is added explaining the stale status
3. Issues remain stale for 7 days before being automatically closed
4. Stale issues that receive activity have the stale label removed

### PR Integration

1. PRs that reference issues with "closes #X" syntax automatically:
   - Add a comment to the linked issue
   - Apply `status: in-review` label to the issue
2. When PRs are merged:
   - Add resolution comment to linked issues
   - Remove `status: in-review` label

## Metrics and Reporting

### Daily Metrics Collection
- Total open/closed issues
- Triage status distribution
- Response time averages
- Label distribution analysis

### Weekly Reporting
Comprehensive reports include:
- Overview statistics
- Triage efficiency metrics
- Response time analysis
- Label distribution
- Contributor activity
- Quality metrics
- Actionable recommendations

### Health Monitoring
The system monitors:
- Issues needing attention (>3 days without triage)
- Stale issues (>30 days without activity)
- Missing essential labels
- High-priority unassigned issues
- Potential duplicate issues

## Manual Controls

### Workflow Dispatch Options

#### Bug Triage Workflow
- `triage_all`: Re-triage all open issues

#### Label Management Workflow
- `sync`: Create/update all labels
- `create-missing`: Only create missing labels
- `audit`: Report on unused/deprecated labels
- `cleanup`: Migrate deprecated labels on issues

#### Issue Management Workflow
- `health-check`: Run issue health analysis
- `close-stale`: Process stale issue closure
- `update-metrics`: Refresh metric calculations
- `sync-labels`: Synchronize label schema

#### Metrics Workflow
- `daily`/`weekly`/`monthly`: Generate period reports
- `custom`: Custom date range analysis

## Best Practices

### For Maintainers

1. **Regular Monitoring**:
   - Check weekly triage reports
   - Review health check notifications
   - Act on escalated high-priority issues

2. **Label Hygiene**:
   - Use consistent labeling patterns
   - Run label sync weekly
   - Audit unused labels monthly

3. **Response Times**:
   - Aim to respond to new issues within 48 hours
   - Prioritize critical and high-priority issues
   - Use template responses for common questions

### For Contributors

1. **Issue Creation**:
   - Use appropriate issue templates
   - Provide complete information requested in templates
   - Check for existing similar issues before creating new ones

2. **Issue Updates**:
   - Respond promptly to requests for additional information
   - Update issues when circumstances change
   - Close issues when resolved independently

## Troubleshooting

### Common Issues

1. **Labels Not Applied**: Check if issue content matches pattern keywords
2. **Assignment Not Working**: Verify component labels are correctly applied
3. **Stale Issues**: Issues marked stale can be reactivated by adding comments
4. **Duplicate Detection**: May flag similar but distinct issues - review carefully

### Manual Overrides

All automated actions can be manually overridden:
- Add/remove labels manually
- Change assignments
- Remove stale status by commenting
- Close/reopen issues as needed

## Configuration

### Environment Variables
No additional environment variables required - system uses GitHub tokens automatically.

### Permissions
Workflows require:
- `issues: write` - For label and assignment management
- `contents: read` - For repository access
- `pull-requests: read` - For PR integration

## Monitoring and Maintenance

### Regular Tasks
1. **Weekly**: Review triage reports and health metrics
2. **Monthly**: Audit label usage and clean up deprecated labels
3. **Quarterly**: Review automation rules and adjust based on repository needs

### Performance Metrics
- Triage time: Target <24 hours for initial triage
- Response time: Target <48 hours for first maintainer response
- Resolution time: Varies by issue complexity and priority
- Stale rate: Target <10% of open issues marked as stale

## Future Enhancements

Potential improvements to consider:
1. **AI-Powered Classification**: Use GitHub Copilot or similar for smarter issue categorization
2. **Integration with External Tools**: Connect to project management tools or monitoring systems
3. **Advanced Duplicate Detection**: Implement semantic similarity matching
4. **Automated Testing**: Trigger relevant tests based on issue components
5. **Community Health Metrics**: Track contributor engagement and satisfaction

---

For questions about the triage automation system, please create an issue with the `type: documentation` label.