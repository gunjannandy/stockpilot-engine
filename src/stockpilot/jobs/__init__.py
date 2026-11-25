"""The jobs `sp tick` runs. `due` decides which one; each job module follows the phase rule: network, the runner,
`wrangler` and git or gh pushes run with the database closed, and it is opened only to write."""
