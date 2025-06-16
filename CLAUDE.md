# Claude AI Context File

## Debugging Lessons Learned

**Variable shadowing and misleading logs**: When debugging AWS region issues, don't trust log statements alone - verify actual API behavior by checking what resources are returned, as local variable overrides can cause clients to use different regions than what logs indicate.