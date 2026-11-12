// Parity check: the browser forecast must reproduce the Python forecasts in
// structural_golden.json (written by scripts/export_structural.py).
//   npm run check:structural
import { readFileSync } from 'node:fs'
import { differenceAtoms, histogram, sideAtoms, summarize } from '../src/lib/structural.ts'

const read = (name) => JSON.parse(readFileSync(new URL(`../src/data/model/${name}`, import.meta.url), 'utf8'))
const { params, players } = read('structural_model.json')
const golden = read('structural_golden.json')
const TOL = 1e-9

const atoms = (ids) => sideAtoms(params, ids.map((id) => players[id]))
const keys = ['mean', 'median', 'p5', 'p95', 'pPositive']
const pyKeys = { mean: 'mean', median: 'median', p5: 'p5', p95: 'p95', pPositive: 'p_positive' }

let worst = 0
let bad = 0
const compare = (label, got, want) => {
  for (const k of keys) {
    const err = Math.abs(got[k] - want[pyKeys[k]])
    worst = Math.max(worst, err)
    if (!(err <= TOL)) {
      bad++
      console.error(`MISMATCH ${label} ${k}: ts=${got[k]} py=${want[pyKeys[k]]}`)
    }
  }
}
golden.sides.forEach((c, i) => compare(`side ${i}`, summarize(atoms(c.ids)), c.expected))
golden.pairs.forEach((c, i) => compare(`pair ${i}`, summarize(differenceAtoms(atoms(c.a), atoms(c.b))), c.expected))

// The distribution plot must not lose or invent probability mass.
for (const [i, c] of golden.pairs.entries()) {
  const mass = histogram(differenceAtoms(atoms(c.a), atoms(c.b)), -40, 40, 41).reduce((a, b) => a + b, 0)
  if (Math.abs(mass - 1) > 1e-9) {
    bad++
    console.error(`MISMATCH histogram mass pair ${i}: ${mass}`)
  }
}

const n = golden.sides.length + golden.pairs.length
console.log(`${n} golden cases, max abs error ${worst.toExponential(2)} (tolerance ${TOL})`)
if (bad > 0) process.exit(1)
