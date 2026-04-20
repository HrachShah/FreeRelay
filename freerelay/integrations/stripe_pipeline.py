[33mcommit 3f0080a0760fcf77fc85fcdd515ff915bae7ee77[m
Merge: 324b127 03cf370
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sun Apr 19 14:39:37 2026 +0000

    Merge pull request #8 from HrachShah/dashboard-minimal-features
    
    Minimal Dashboard: Auth, API Keys, and Usage Summary

[33mcommit 324b1278a5e8510c082b2f8a0377eda3b6680f57[m
Merge: d1fcec6 78776a4
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sun Apr 19 14:38:29 2026 +0000

    Merge pull request #7 from HrachShah/dashboard-roi-viz
    
    Dashboard: Savings & ROI Visualization

[33mcommit d1fcec61d9680f7107be33b36414d5dcc4cf2878[m
Merge: b2d6c96 90b6258
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sun Apr 19 14:38:17 2026 +0000

    Merge pull request #6 from HrachShah/dashboard-init
    
    Initialize Next.js dashboard with shadcn/ui and recharts

[33mcommit cfadbac283bfb81f7c1bc896cb7c69057ead3820[m
Merge: 52ea9d7 055c2c7
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sun Apr 19 11:54:02 2026 +0000

    Merge pull request #4 from HrachShah/cto/feat-prod-mvp-refine-auth-billing-join
    
    Implement Production MVP: Auth, Usage Tracking, and Billing

[33mcommit 055c2c75147c20e65d3ecde140da9367cee18cd0[m[33m ([m[1;31morigin/cto/feat-prod-mvp-refine-auth-billing-join[m[33m, [m[1;32mcto/feat-prod-mvp-refine-auth-billing-join[m[33m)[m
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sun Apr 19 11:51:33 2026 +0000

    feat: implement production MVP with Supabase auth, usage tracking, and Stripe integration
    
    - Added Supabase schema for users, api_keys, and usage_logs.
    - Refined AuthMiddleware to support Supabase-backed dynamic API keys and user identity tracking.
    - Updated RoutingEngine and RequestContext to support multi-tenancy and user-aware routing.
    - Enhanced usage tracking to log user_id with every request, including streaming estimation.
    - Fully implemented /v1/auth/register and added /v1/billing/webhook for Stripe integration.
    - Updated requirements.txt and pyproject.toml with new dependencies.
    - Refined README.md and .env.example with production setup instructions.

[33mcommit 52ea9d734fab292a544600e467ff83425c0e1650[m
Merge: b0b519e 02230ed
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sat Apr 18 22:40:22 2026 +0000

    Merge pull request #3 from HrachShah/cto/implement-supabase-auth-models-stripe-integration
    
    Engine: Task changes

[33mcommit 02230eda68013feb25c0b94fc2043e24a4916079[m[33m ([m[1;31morigin/cto/implement-supabase-auth-models-stripe-integration[m[33m)[m
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sat Apr 18 22:40:07 2026 +0000

    WIP: partial changes from incomplete task

[33mcommit b0b519efa725328b765cb79a183a990845558418[m
Merge: b3610ba 4d9dc83
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sat Apr 18 22:26:45 2026 +0000

    Merge pull request #2 from HrachShah/cto/fix-obscurored-add-ask-command
    
    Fix CLI bug and add 'ask' command with provider routing

[33mcommit 4d9dc83f7361a27109fb310c274183d10b8bc47a[m[33m ([m[1;31morigin/cto/fix-obscurored-add-ask-command[m[33m)[m
Author: [1;31mcto-new[bot][m <140088366+[1;31mcto-new[bot][m@users.noreply.github.com>
Date:   Sat Apr 18 22:26:16 2026 +0000

    fix: CLI 'obscurored' typo and add 'ask' command with provider forcing support
    
    - Fixed 'obscurored' typo in freerelay/cli/main.py.
    - Created freerelay/core/routing/factory.py to centralize RoutingEngine initialization.
    - Refactored freerelay/main.py to use the new engine factory.
    - Implemented 'ask' command in the CLI for direct LLM interaction.
    - Updated RoutingEngine to support forcing specific providers via model name prefix (e.g., freerelay-groq).
    - Added support for specifying both provider and model in the CLI (e.g., --provider groq --model llama3).
