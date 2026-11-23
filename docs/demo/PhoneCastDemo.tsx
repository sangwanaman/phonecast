import { Avatar, Bar, Collapse, Count, Field, Popover, Roll, Stage, Toast, Toggle, type Act } from '../../kit'
import './demo.css'

// The README demo for PhoneCast, built with Stageshow.
//
// The real app is a phone-shaped window: the phone's screen edge to edge, a thin column of
// icon buttons and a bottom bar with the phone's name. Shown whole on a quiet ground, since
// the story needs both the title bar and the bottom bar. Four beats: type a search on the
// phone from the PC keyboard, open the phone picker, switch to a second phone, start a
// recording. The reset is seen: stop the recording, switch back.
//
// Real words: the phone names, their battery, the search, the conversation names and the
// alarm times. Everything else is placeholder lines.
//
// Copy this folder into stageshow/examples/phonecast/ to preview or film it there; the kit is
// imported from ../../kit.

type Phone = 'galaxy' | 'redmi'
type S = {
  phone: Phone
  query: string
  searching: boolean
  menu: boolean
  toast: boolean
  recording: boolean
  secs: number
}

const initial: S = { phone: 'galaxy', query: '', searching: false, menu: false, toast: false, recording: false, secs: 0 }
const POSTER: S = { ...initial, phone: 'redmi', recording: true, secs: 3 }

const PHONES: Record<Phone, { name: string; battery: number }> = {
  galaxy: { name: 'Galaxy S21 FE', battery: 88 },
  redmi: { name: 'Redmi Note 4', battery: 64 },
}

// Segoe Fluent Icons, the app's own icon font (built into Windows 11)
const G = {
  back: '', home: '', recents: '', notifications: '', quick: '',
  volUp: '', volDown: '', power: '', rotate: '', unlock: '',
  mouse: '', keyboard: '', sound: '', screenOff: '', eye: '',
  camera: '', record: '', stop: '', hdmi: '', pin: '',
  compact: '', full: '', settings: '', more: '', usb: '',
  check: '', wifi: '', link: '', search: '', add: '',
  min: '', max: '', close: '', tv: '',
}

const CONVERSATIONS = [
  { name: 'Riya', preview: [150, 96], time: '10:24' },
  { name: 'Mom', preview: [120], time: '9:58' },
  { name: 'Kabir', preview: [138, 70], time: '9:12' },
  { name: 'Cricket club', preview: [110], time: 'Tue' },
  { name: 'Dad', preview: [128], time: 'Mon' },
  { name: 'Ananya', preview: [144, 82], time: 'Sun' },
]

const ALARMS = [
  { time: '6:30', half: 'AM', days: 74, on: true },
  { time: '7:15', half: 'AM', days: 52, on: false },
  { time: '9:00', half: 'AM', days: 64, on: true },
  { time: '10:30', half: 'AM', days: 40, on: false },
  { time: '1:45', half: 'PM', days: 58, on: false },
  { time: '10:00', half: 'PM', days: 70, on: true },
  { time: '11:30', half: 'PM', days: 48, on: false },
]

const REST = { x: 214, y: 610 }

async function script(a: Act<S>) {
  await a.wait(700)

  // 1. Typing on the phone, from the computer's keyboard
  await a.move('search')
  await a.click()
  await a.set({ searching: true })
  await a.wait(200)
  await a.type('query', 'Riya', { interval: 90 })
  await a.wait(700)

  // 2. The phone picker opens above the phone's name
  await a.move({ at: 'pill', x: 0.93, y: 0.5 })   // on the chevron, off the name
  await a.wait(150)
  await a.click()
  await a.set({ menu: true })
  await a.wait(550)

  // 3. Switch to the other phone
  await a.move({ at: 'to-redmi', x: 0.6, y: 0.5 })   // the gap between name and battery, off the words
  await a.wait(250)
  await a.click()
  await a.set({ menu: false })
  await a.wait(120)
  a.mark('switch')
  await a.set({ phone: 'redmi', toast: true })
  await a.move(REST)
  await a.wait(1300)
  // the first phone's screen has faded out: put its search back unseen, touching nothing else
  await a.snap({ query: '', searching: false }, 'screen-galaxy')
  await a.set({ toast: false })

  // 4. Record the screen
  await a.move({ at: 'record', x: 0.5, y: 0.92 })   // the button's lower edge, off the glyph
  await a.wait(200)
  await a.click()
  await a.set({ recording: true, secs: 0 })
  for (let i = 1; i <= 3; i++) {
    await a.wait(1000)
    await a.set({ secs: i })
  }
  await a.wait(600)

  // Reset, seen: stop recording, switch back
  await a.click({ at: 'record', x: 0.5, y: 0.92 })
  await a.set({ recording: false })
  await a.wait(350)
  await a.move({ at: 'pill', x: 0.93, y: 0.5 })
  await a.click()
  await a.set({ menu: true })
  await a.wait(450)
  await a.move({ at: 'to-galaxy', x: 0.6, y: 0.5 })
  await a.click()
  await a.set({ menu: false })
  await a.wait(120)
  await a.set({ phone: 'galaxy', secs: 0 })
  await a.move(REST)
  await a.wait(900)
}

function TitleBar({ name }: { name: string }) {
  return (
    <div className="ctv-titlebar">
      <span className="ctv-appicon" aria-hidden>{G.tv}</span>
      <span className="ctv-title">PhoneCast · <Roll>{name}</Roll></span>
      <span className="ctv-caption" aria-hidden data-crop>
        <span>{G.min}</span><span>{G.max}</span><span>{G.close}</span>
      </span>
    </div>
  )
}

function Messages({ s }: { s: S }) {
  const q = s.query.toLowerCase()
  return (
    <div className="ctv-app">
      <div className="ctv-app-title">Messages</div>
      <Field
        className="ctv-search"
        value={s.query}
        placeholder="Search conversations"
        focused={s.searching}
        leading={<span className="ctv-glyph">{G.search}</span>}
        box={{ 'data-target': 'search', 'data-cursor': 'ibeam' }}
      />
      <div className="ctv-list">
        {CONVERSATIONS.map((c) => (
          <Collapse key={c.name} open={!q || c.name.toLowerCase().startsWith(q)}>
            <div className="ctv-convo">
              <Avatar name={c.name} size={36} />
              <div className="ctv-convo-text">
                <div className="ctv-convo-top">
                  <span className="ctv-convo-name">{c.name}</span>
                  <span className="ctv-convo-time">{c.time}</span>
                </div>
                {c.preview.map((w, i) => <Bar key={i} w={w} h={5} tone={2} />)}
              </div>
            </div>
          </Collapse>
        ))}
      </div>
      <span className="ctv-fab" aria-hidden>{G.add}</span>
    </div>
  )
}

function Alarms() {
  return (
    <div className="ctv-app">
      <div className="ctv-app-title">Alarm</div>
      <div className="ctv-alarms">
        {ALARMS.map((al) => (
          <div key={al.time} className="ctv-alarm" data-on={al.on || undefined}>
            <div>
              <div className="ctv-alarm-time">{al.time}<span className="ctv-alarm-ampm">{al.half}</span></div>
              <Bar w={al.days} h={5} tone={2} />
            </div>
            <Toggle on={al.on} />
          </div>
        ))}
      </div>
      <span className="ctv-fab" aria-hidden>{G.add}</span>
    </div>
  )
}

function Screen({ s }: { s: S }) {
  return (
    // the phone's picture runs edge to edge: no padding, on purpose
    <div className="ctv-screen" data-crop>
      <div className="ctv-statusbar">
        <span>10:24</span>
        <span className="ctv-glyph">{G.wifi}</span>
      </div>
      <div className="ctv-layer" data-target="screen-galaxy" data-active={s.phone === 'galaxy' || undefined}><Messages s={s} /></div>
      <div className="ctv-layer ctv-layer--redmi" data-active={s.phone === 'redmi' || undefined}><Alarms /></div>
      <div className="ctv-toast-slot">
        <Toast show={s.toast}>Connected to Redmi Note 4</Toast>
      </div>
    </div>
  )
}

const DOCK: { g: string; on?: boolean; target?: string; gap?: boolean }[] = [
  { g: G.back }, { g: G.home }, { g: G.recents, gap: true },
  { g: G.notifications }, { g: G.quick, gap: true },
  { g: G.volUp }, { g: G.volDown }, { g: G.power }, { g: G.rotate }, { g: G.unlock, gap: true },
  { g: G.mouse, on: true }, { g: G.keyboard, on: true, gap: true },
  { g: G.sound, on: true }, { g: G.screenOff }, { g: G.eye, on: true }, { g: G.camera }, { g: G.record, target: 'record' },
]
const DOCK_END = [G.hdmi, G.pin, G.compact, G.full, G.settings, G.more]

function Dock({ s }: { s: S }) {
  return (
    <div className="ctv-dock">
      {DOCK.map((b, i) => {
        const rec = b.target === 'record'
        return (
          <span
            key={i}
            className="ctv-dock-btn"
            data-on={b.on || undefined}
            data-rec={(rec && s.recording) || undefined}
            data-gap={b.gap || undefined}
            data-target={b.target}
            data-cursor={b.target ? 'pointer' : undefined}
          >
            {rec && s.recording ? G.stop : b.g}
          </span>
        )
      })}
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
      <span className="ctv-menu-detail">USB · {PHONES[p].battery}%</span>
    </div>
  )
  return (
    <Popover show={s.menu} origin="bottom left" className="ctv-menu">
      <div className="ctv-menu-head">Phones</div>
      {row('galaxy', 'to-galaxy')}
      {row('redmi', 'to-redmi')}
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
  // a plain ticking timer, as the app shows it
  const time = `${String(Math.floor(s.secs / 60)).padStart(2, '0')}:${String(s.secs % 60).padStart(2, '0')}`
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
      <span className="ctv-rec" data-show={s.recording || undefined}>
        ● {time}
      </span>
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
      cursor={{ at: REST, style: 'arrow', ripple: true }} className="ctv">
      {(s) => (
        <div className="ctv-window">
          <TitleBar name={PHONES[s.phone].name} />
          <div className="ctv-body">
            <Screen s={s} />
            <Dock s={s} />
          </div>
          <BottomBar s={s} />
          <PhoneMenu s={s} />
        </div>
      )}
    </Stage>
  )
}
