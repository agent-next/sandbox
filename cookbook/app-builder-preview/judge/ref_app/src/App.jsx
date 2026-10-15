// Judge-controlled reference app for the app-builder-preview demo.
//
// It is not graded; it is the oracle the graded artifact is compared with.
// It is deliberately written differently from examples/good/app: a Map for
// the todos, a data-id lookup for every item action, a stored filter that
// is applied only at render time, and no StrictMode wrapper. If the judge
// (or the spec) is wrong, the reference disagrees with a correct artifact
// and gate 5 fails - which is exactly the check SPEC.md describes.
import { useState, useEffect } from 'react'

const SPEC_PATH = '/spec.json'
const STORE_KEY = 'todo-reflist'

async function loadSpec() {
  const res = await fetch(SPEC_PATH)
  if (!res.ok) throw new Error(`spec.json: HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const [spec, setSpec] = useState(null)
  const [todos, setTodos] = useState([])
  const [text, setText] = useState('')
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    loadSpec().then(setSpec).catch(console.error)
  }, [])

  useEffect(() => {
    const saved = localStorage.getItem(STORE_KEY)
    if (saved) {
      try {
        setTodos(JSON.parse(saved))
      } catch {
        localStorage.removeItem(STORE_KEY)
      }
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORE_KEY, JSON.stringify(todos))
  }, [todos])

  if (!spec) return <div id="ref-loading">loading</div>

  // The element names in spec.json are the DOM ids (its values are the
  // human descriptions); the judge drives exactly those names.
  const ids = Object.fromEntries(
    Object.keys(spec.elements).map(name => [name, name])
  )
  const order = todos.map(t => t.id)

  const byId = id => todos.find(t => t.id === id)

  function add() {
    const value = text.trim()
    if (!value) return
    setTodos([...todos, { id: `t${order.length}-${value}`, text: value, done: false }])
    setText('')
  }

  function toggle(id) {
    setTodos(todos.map(t => (t.id === id ? { ...t, done: !t.done } : t)))
  }

  function remove(id) {
    setTodos(todos.filter(t => t.id !== id))
  }

  function shown() {
    if (filter === 'active') return order.filter(i => !byId(i).done)
    if (filter === 'done') return order.filter(i => byId(i).done)
    return order
  }

  const doneCount = todos.reduce((n, t) => n + (t.done ? 1 : 0), 0)

  const filterButton = (key, label) => (
    <button id={ids[`filter-${key}`]}
            className={filter === key ? 'active' : undefined}
            onClick={() => setFilter(key)}>{label}</button>
  )

  return (
    <div id="app">
      <h1>{spec.app}</h1>
      <p>
        <input id={ids['todo-input']} value={text}
               onChange={e => setText(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') add() }} />
        <button id={ids['todo-add']} onClick={add}>add</button>
      </p>
      <ul id={ids['todo-list']}>
        {shown().map(id => {
          const todo = byId(id)
          return (
            <li key={id} id={ids['todo-item']} data-id={id}
                className={todo.done ? 'done' : undefined}>
              <span id={ids['todo-text']}>{todo.text}</span>
              <button id={ids['todo-toggle']} onClick={() => toggle(id)}>
                {todo.done ? 'undone' : 'done'}
              </button>
              <button id={ids['todo-delete']} onClick={() => remove(id)}>
                remove
              </button>
            </li>
          )
        })}
      </ul>
      <p>
        {filterButton('all', 'all')}
        {filterButton('active', 'active')}
        {filterButton('done', 'done')}
      </p>
      <p>
        total <span id={ids['stats-total']}>{todos.length}</span>
        active <span id={ids['stats-active']}>{todos.length - doneCount}</span>
        done <span id={ids['stats-done']}>{doneCount}</span>
      </p>
    </div>
  )
}
