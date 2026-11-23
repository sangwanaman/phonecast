import { Avatar, Bubble, Count, Popover, Roll, Stage, Stamp, Thread, Toast, type Act } from '../../kit'
import './demo.css'

// The README demo for PhoneCast, built with Stageshow.
//
// What the app is for, in one loop: use your phone from the computer. The real app is a
// phone-shaped window (the phone's screen edge to edge, a thin column of icon buttons, a bottom
// bar with the phone's name), shown whole on a quiet ground since the story needs the title bar
// and the bottom bar. Three beats:
//   1. On a Galaxy S21 FE, a chat reply typed on the computer's keyboard and sent.
//   2. The phone picker opens above the phone's name; switch to a Galaxy S24 Ultra.
//   3. Ctrl+V (keycaps on screen) pastes the computer's clipboard into a note on that phone.
// The reset is seen: switch back. The sent message leaves while its phone is hidden.
//
// Real words: phone names and battery, the conversation, the note. The rest is placeholder lines.
//
// Copy this folder into stageshow/examples/phonecast/ to preview or film it there; the kit is
// imported from ../../kit.

type Phone = 's21' | 's24'
type S = {
  phone: Phone
  draft: string
  sent: boolean
  menu: boolean
  toast: boolean
  editing: boolean
  pasted: boolean
}

const initial: S = { phone: 's21', draft: '', sent: false, menu: false, toast: false, editing: false, pasted: false }
const POSTER: S = { ...initial, phone: 's24', editing: true, pasted: true }

const PHONES: Record<Phone, { name: string; battery: number }> = {
  s21: { name: 'Galaxy S21 FE', battery: 88 },
  s24: { name: 'Galaxy S24 Ultra', battery: 72 },
}

const REPLY = 'Leaving now, see you at 8'
const CLIPBOARD = 'Flight AI 865 · Gate 32 · Boards 6:40 PM'

// Segoe Fluent Icons, the app's own icon font (built into Windows 11)
const G = {
  back: '', home: '', recents: '', notifications: '', quick: '',
  volUp: '', volDown: '', power: '', rotate: '', unlock: '',
  mouse: '', keyboard: '', sound: '', screenOff: '', eye: '',
  camera: '', record: '', hdmi: '', pin: '',
  compact: '', full: '', settings: '', more: '', usb: '',
  check: '', wifi: '', link: '', add: '', send: '',
  min: '', max: '', close: '', navBack: '', attach: '',
}

const REST = { x: 200, y: 330 }

async function script(a: Act<S>) {
  await a.wait(700)

  // 1. Reply from the computer's keyboard
  await a.click('compose')
  await a.type('draft', REPLY, { interval: 55 })
  await a.wait(400)
  await a.click({ at: 'send', x: 0.5, y: 0.85 })
  // the field clears in the same update that adds the bubble: the words lift out of it
  await a.set({ sent: true, draft: '' })
  await a.move(REST)
  await a.wait(1100)

  // 2. The phone picker opens above the phone's name; switch phones
  await a.move({ at: 'pill', x: 0.94, y: 0.5 })   // on the chevron, off the name
  await a.wait(150)
  await a.click()
  await a.set({ menu: true })
  await a.wait(550)
  await a.move({ at: 'to-s24', x: 0.62, y: 0.5 })  // the gap between name and battery
  await a.wait(250)
  await a.click()
  await a.set({ menu: false })
  await a.wait(120)
  a.mark('switch')
  await a.set({ phone: 's24', toast: true })
  await a.move(REST)
  await a.wait(1200)
  // the first phone has faded out: its sent message leaves unseen, touching nothing else
  await a.snap({ sent: false }, 'screen-s21')
  await a.set({ toast: false })

  // 3. Paste the computer's clipboard into a note
  await a.click({ at: 'note', x: 0.7, y: 0.75 })
  await a.set({ editing: true })
  await a.wait(450)
  await a.key('ctrl+v')
  await a.set({ pasted: true })
  await a.move(REST)
  await a.wait(2200)

  // Reset, seen: switch back
  await a.move({ at: 'pill', x: 0.94, y: 0.5 })
  await a.click()
  await a.set({ menu: true })
  await a.wait(450)
  await a.move({ at: 'to-s21', x: 0.62, y: 0.5 })
  await a.click()
  await a.set({ menu: false })
  await a.wait(120)
  await a.set({ phone: 's21' })
  await a.move(REST)
  await a.wait(700)
  await a.snap({ editing: false, pasted: false }, 'screen-s24')
  await a.wait(300)
}

function TitleBar({ name }: { name: string }) {
  return (
    <div className="ctv-titlebar">
      <svg className="ctv-appicon" viewBox="0 0 512 512" aria-hidden>
        <defs>
          <linearGradient id="ctv-tile" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a9dff" />
            <stop offset="1" stopColor="#0866d6" />
          </linearGradient>
        </defs>
        <rect width="512" height="512" rx="116" fill="url(#ctv-tile)" />
        <rect x="112" y="100" width="172" height="312" rx="38" fill="none" stroke="#fff" strokeWidth="34" />
        <path d="M 314 206 A 62 62 0 0 1 314 306" fill="none" stroke="#fff" strokeWidth="34" strokeLinecap="round" />
      </svg>
      <span className="ctv-title">PhoneCast · <Roll>{name}</Roll></span>
      <span className="ctv-caption" aria-hidden data-crop>
        <span>{G.min}</span><span>{G.max}</span><span>{G.close}</span>
      </span>
    </div>
  )
}

function Chat({ s }: { s: S }) {
  return (
    <div className="ctv-app ctv-chat">
      <div className="ctv-chat-head">
        <span className="ctv-glyph">{G.navBack}</span>
        <Avatar name="Riya" size={30} />
        <span className="ctv-chat-name">Riya</span>
      </div>
      <Thread className="ctv-thread">
        <Stamp>Yesterday 9:10 PM</Stamp>
        <Bubble from="them">Did you book the movie tickets?</Bubble>
        <Bubble from="me">Yes, two seats for Saturday</Bubble>
        <Bubble from="them">Nice! What time is the show?</Bubble>
        <Bubble from="me">8:30, I'll send you the tickets</Bubble>
        <Stamp>Today 7:42 PM</Stamp>
        <Bubble from="them">Are you still coming tonight?</Bubble>
        <Bubble from="them">Dinner's at 8, the place near the station</Bubble>
        {s.sent && <Bubble from="me" source="draft">{REPLY}</Bubble>}
      </Thread>
      <div className="ctv-compose">
        <span className="ctv-glyph ctv-attach">{G.attach}</span>
        <span className="ctv-field" data-target="compose" data-cursor="ibeam">
          <span className="ctv-field-text" data-target="draft">
            {s.draft}
            {s.draft && <i className="ctv-caret" data-snap />}
          </span>
          <span className="ctv-field-ph" data-hide={s.draft ? '' : undefined}>Text message</span>
        </span>
        <span className="ctv-send" data-target="send" data-cursor="pointer" data-show={s.draft ? '' : undefined}>
          <span className="ctv-glyph">{G.send}</span>
        </span>
      </div>
    </div>
  )
}

function Notes({ s }: { s: S }) {
  return (
    <div className="ctv-app ctv-notes">
      <div className="ctv-notes-head">
        <span className="ctv-glyph">{G.navBack}</span>
        <span className="ctv-notes-folder">Notes</span>
      </div>
      <div className="ctv-note" data-target="note" data-cursor="ibeam">
        <div className="ctv-note-title">Trip to Goa</div>
        <div className="ctv-note-line">Pack the charger and power bank</div>
        <div className="ctv-note-line">Sunscreen and sunglasses</div>
        <div className="ctv-note-line">Book the beach shack for Sunday</div>
        <div className="ctv-note-line">Cab to the airport at 4:30</div>
        <div className="ctv-note-sub">Flight</div>
        <div className="ctv-note-paste" data-show={s.pasted || undefined}>{CLIPBOARD}</div>
        <div className="ctv-note-caret" data-show={(s.editing && !s.pasted) || undefined} data-snap />
      </div>
    </div>
  )
}

function Screen({ s }: { s: S }) {
  return (
    // the phone's picture runs edge to edge: no padding, on purpose
    <div className="ctv-screen" data-crop>
      <div className="ctv-statusbar">
        <span>7:45</span>
        <span className="ctv-glyph">{G.wifi}</span>
      </div>
      <div className="ctv-layer" data-target="screen-s21" data-active={s.phone === 's21' || undefined}><Chat s={s} /></div>
      <div className="ctv-layer ctv-layer--s24" data-target="screen-s24" data-active={s.phone === 's24' || undefined}><Notes s={s} /></div>
      <div className="ctv-toast-slot">
        <Toast show={s.toast}>Connected to Galaxy S24 Ultra</Toast>
      </div>
    </div>
  )
}

const DOCK: { g: string; on?: boolean; gap?: boolean }[] = [
  { g: G.back }, { g: G.home }, { g: G.recents, gap: true },
  { g: G.notifications }, { g: G.quick, gap: true },
  { g: G.volUp }, { g: G.volDown }, { g: G.power }, { g: G.rotate }, { g: G.unlock, gap: true },
  { g: G.mouse, on: true }, { g: G.keyboard, on: true, gap: true },
  { g: G.sound, on: true }, { g: G.screenOff }, { g: G.eye, on: true }, { g: G.camera }, { g: G.record },
]
const DOCK_END = [G.hdmi, G.pin, G.compact, G.full, G.settings, G.more]

function Dock() {
  return (
    <div className="ctv-dock">
      {DOCK.map((b, i) => (
        <span key={i} className="ctv-dock-btn" data-on={b.on || undefined} data-gap={b.gap || undefined}>{b.g}</span>
      ))}
      <span className="ctv-dock-fill" />
      {DOCK_END.map((g) => <span key={g} className="ctv-dock-btn">{g}</span>)}
    </div>
  )
}

function PhoneMenu({ s }: { s: S }) {
  const row = (p: Phone, target: string) => (
    <div className="ctv-menu-row" data-current={s.phone === p || undefined} data-target={target} data-cursor="pointer">
      <span className="ctv-glyph ctv-menu-icon">{s.phone === p ? G.check : G.usb}</span>
      <span className="ctv-menu-name">{PHONES[p].name}</span>
      <span className="ctv-menu-detail">{PHONES[p].battery}%</span>
    </div>
  )
  return (
    <Popover show={s.menu} origin="bottom left" className="ctv-menu">
      <div className="ctv-menu-head">Phones</div>
      {row('s21', 'to-s21')}
      {row('s24', 'to-s24')}
      <div className="ctv-menu-sep" />
      <div className="ctv-menu-row ctv-menu-row--quiet">
        <span className="ctv-glyph ctv-menu-icon">{G.link}</span>
        <span className="ctv-menu-name">Connect over Wi-Fi…</span>
      </div>
    </Popover>
  )
}

function BottomBar({ s }: { s: S }) {
  const phone = PHONES[s.phone]
  return (
    <div className="ctv-bar">
      <span className="ctv-pill" data-target="pill" data-cursor="pointer" data-open={s.menu || undefined}>
        <span className="ctv-dot" />
        <Roll>{phone.name}</Roll>
        <span className="ctv-more">+1</span>
        <span className="ctv-chevron">▾</span>
      </span>
      <span className="ctv-glyph ctv-via">{G.usb}</span>
      <span className="ctv-bar-fill" />
      <span className="ctv-battery">
        <Count value={phone.battery} format={(n) => `${Math.round(n)}%`} />
        <span className="ctv-battery-body"><span style={{ width: `${phone.battery}%` }} /></span>
      </span>
    </div>
  )
}

export function PhoneCastDemo() {
  return (
    <Stage width={400} height={760} theme="dark" initial={initial} poster={POSTER} script={script}
      cursor={{ at: REST, style: 'arrow', ripple: true }} keys="bottom" className="ctv">
      {(s) => (
        <div className="ctv-window">
          <TitleBar name={PHONES[s.phone].name} />
          <div className="ctv-body">
            <Screen s={s} />
            <Dock />
          </div>
          <BottomBar s={s} />
          <PhoneMenu s={s} />
        </div>
      )}
    </Stage>
  )
}
