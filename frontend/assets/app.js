const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

const state = {
  token: localStorage.getItem("hotel_token"),
  user: JSON.parse(localStorage.getItem("hotel_user") || "null"),
  view: "dashboard",
  rooms: [],
  customers: [],
  reservations: [],
  stays: [],
};

const pageMeta = {
  dashboard: ["今日运营", "总览"],
  rooms: ["房态实时更新", "客房管理"],
  reservations: ["预订冲突校验", "预订管理"],
  checkins: ["入住登记", "办理入住"],
  stays: ["额外消费与结算", "退房结算"],
  customers: ["入住历史", "客户档案"],
  reports: ["日月年统计", "经营报表"],
  audit: ["操作留痕", "审计日志"],
};

const roleMap = {
  admin: "系统管理员",
  frontdesk: "前台",
  housekeeping: "客房部",
  finance: "财务",
};

const statusMap = {
  free: "空闲",
  occupied: "入住",
  reserved: "预订",
  maintenance: "维修",
};

const reservationStatusMap = {
  pending: "待确认",
  confirmed: "已确认",
  cancelled: "已取消",
  checked_in: "已入住",
  no_show: "未到店",
};

const sourceMap = {
  walk_in: "散客",
  member: "会员",
  ota: "OTA",
  company: "协议客户",
  travel_agency: "旅行社",
  other: "其他",
};

const categoryMap = {
  food: "餐饮",
  laundry: "洗衣",
  minibar: "迷你吧",
  parking: "停车",
  damage: "赔偿",
  other: "其他",
};

const paymentMap = {
  cash: "现金",
  wechat: "微信",
  alipay: "支付宝",
  card: "银行卡",
  bank: "转账",
  member: "会员卡",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  bindShell();
  if (state.token && state.user) {
    showApp();
    renderCurrentView();
  } else {
    showLogin();
  }
});

function bindShell() {
  $("#loginForm").addEventListener("submit", handleLogin);
  $$(".demo-accounts button").forEach((button) => {
    button.addEventListener("click", () => {
      const [username, password] = button.dataset.account.split(":");
      $("#loginForm").username.value = username;
      $("#loginForm").password.value = password;
    });
  });
  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $("#logoutBtn").addEventListener("click", logout);
  $("#refreshBtn").addEventListener("click", renderCurrentView);
  $("#modalClose").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (event) => {
    if (event.target.id === "modal") closeModal();
  });
  document.addEventListener("click", handleActionClick);
  document.addEventListener("submit", handleFormSubmit);
}

async function handleLogin(event) {
  event.preventDefault();
  const data = serialize(event.target);
  try {
    const result = await api("/api/login", { method: "POST", body: data, auth: false });
    state.token = result.token;
    state.user = result.user;
    localStorage.setItem("hotel_token", state.token);
    localStorage.setItem("hotel_user", JSON.stringify(state.user));
    showApp();
    await setView("dashboard");
    toast("登录成功");
  } catch (error) {
    toast(error.message, true);
  }
}

function showLogin() {
  $("#loginView").classList.remove("is-hidden");
  $("#appView").classList.add("is-hidden");
}

function showApp() {
  $("#loginView").classList.add("is-hidden");
  $("#appView").classList.remove("is-hidden");
  $("#userName").textContent = state.user.display_name;
  $("#userRole").textContent = roleMap[state.user.role] || state.user.role;
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("hotel_token");
  localStorage.removeItem("hotel_user");
  showLogin();
}

async function setView(view) {
  state.view = view;
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  const [eyebrow, title] = pageMeta[view];
  $("#pageEyebrow").textContent = eyebrow;
  $("#pageTitle").textContent = title;
  await renderCurrentView();
}

async function renderCurrentView() {
  const content = $("#content");
  content.innerHTML = `<div class="empty">数据加载中...</div>`;
  try {
    if (state.view === "dashboard") await renderDashboard();
    if (state.view === "rooms") await renderRooms();
    if (state.view === "reservations") await renderReservations();
    if (state.view === "checkins") await renderCheckins();
    if (state.view === "stays") await renderStays();
    if (state.view === "customers") await renderCustomers();
    if (state.view === "reports") await renderReports();
    if (state.view === "audit") await renderAudit();
  } catch (error) {
    if (error.status === 401) logout();
    content.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    toast(error.message, true);
  }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (options.auth !== false && state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(API_BASE + path, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = new Error(data.error || "请求失败");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function renderDashboard() {
  const data = await api("/api/dashboard");
  $("#content").innerHTML = `
    <section class="kpi-grid">
      ${kpi("入住率", `${data.rooms.occupancy_rate}%`, `${data.rooms.occupied}/${data.rooms.total} 间入住`)}
      ${kpi("今日收入", moneyText(data.business.today_income), "已完成结算")}
      ${kpi("本月收入", moneyText(data.business.month_income), "按结算时间汇总")}
      ${kpi("今日到店", data.business.today_arrivals, "确认预订")}
      ${kpi("应退房", data.business.due_departures, "含超时待处理")}
    </section>
    <section class="split-grid">
      <div class="panel">
        <div class="panel-head"><h3>在住客人</h3><button class="secondary-btn" data-view-jump="stays" type="button">结算台</button></div>
        ${activeStayTable(data.active_stays)}
      </div>
      <div class="panel">
        <div class="panel-head"><h3>房态结构</h3></div>
        <div class="bar-list">
          ${statusBar("空闲", data.rooms.free, data.rooms.total, "var(--green)")}
          ${statusBar("入住", data.rooms.occupied, data.rooms.total, "var(--teal)")}
          ${statusBar("预订", data.rooms.reserved, data.rooms.total, "var(--amber)")}
          ${statusBar("维修", data.rooms.maintenance, data.rooms.total, "var(--coral)")}
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>最近结算</h3></div>
      ${recentBillTable(data.recent_bills)}
    </section>
  `;
}

async function renderRooms(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.keyword) params.set("keyword", filters.keyword);
  state.rooms = await api(`/api/rooms${params.toString() ? `?${params}` : ""}`);
  $("#content").innerHTML = `
    <section class="panel">
      <form id="roomFilter" class="toolbar">
        <div class="toolbar-group">
          <input name="keyword" placeholder="房号 / 房型" value="${escapeAttr(filters.keyword || "")}" />
          <select name="status">
            <option value="">全部房态</option>
            ${option("free", "空闲", filters.status)}
            ${option("occupied", "入住", filters.status)}
            ${option("reserved", "预订", filters.status)}
            ${option("maintenance", "维修", filters.status)}
          </select>
          <button class="secondary-btn" type="submit">筛选</button>
        </div>
        <button class="primary-btn" data-action="open-room-modal" type="button">新增客房</button>
      </form>
    </section>
    <section class="room-grid">
      ${state.rooms.map(roomCard).join("") || `<div class="empty">没有匹配的客房</div>`}
    </section>
  `;
}

async function renderReservations(status = "") {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const [rooms, reservations] = await Promise.all([api("/api/rooms"), api(`/api/reservations${params}`)]);
  state.rooms = rooms;
  state.reservations = reservations;
  const tomorrow = addDays(new Date(), 1);
  const afterTomorrow = addDays(new Date(), 2);
  $("#content").innerHTML = `
    <section class="split-grid">
      <form id="reservationForm" class="panel form-grid">
        <h3 class="full">新增预订</h3>
        ${customerFields()}
        <label>房间
          <select name="room_id" required>${roomOptions(rooms, null, true)}</select>
        </label>
        <label>渠道
          <select name="channel">
            <option value="frontdesk">前台</option>
            <option value="OTA">OTA</option>
            <option value="company">协议客户</option>
            <option value="phone">电话</option>
          </select>
        </label>
        <label>入住日期<input type="date" name="checkin_date" value="${dateInput(tomorrow)}" required /></label>
        <label>离店日期<input type="date" name="checkout_date" value="${dateInput(afterTomorrow)}" required /></label>
        <label>订金<input type="number" name="deposit" min="0" step="0.01" value="200" /></label>
        <label class="full">备注<textarea name="notes" placeholder="高楼层、无烟房等"></textarea></label>
        <div class="form-actions"><button class="primary-btn" type="submit">保存预订</button></div>
      </form>
      <div class="panel">
        <div class="panel-head">
          <h3>预订列表</h3>
          <select id="reservationStatusFilter" aria-label="预订状态">
            <option value="">全部</option>
            ${option("pending", "待确认", status)}
            ${option("confirmed", "已确认", status)}
            ${option("checked_in", "已入住", status)}
            ${option("cancelled", "已取消", status)}
          </select>
        </div>
        ${reservationTable(reservations)}
      </div>
    </section>
  `;
  $("#reservationStatusFilter").addEventListener("change", (event) => renderReservations(event.target.value));
}

async function renderCheckins() {
  const rooms = await api("/api/rooms");
  state.rooms = rooms;
  const today = new Date();
  const tomorrow = addDays(today, 1);
  $("#content").innerHTML = `
    <section class="split-grid">
      <form id="checkinForm" class="panel form-grid">
        <h3 class="full">直接入住</h3>
        ${customerFields()}
        <label>房间
          <select name="room_id" required>${roomOptions(rooms, null, true)}</select>
        </label>
        <label>房价
          <input type="number" name="room_rate" min="1" step="0.01" placeholder="默认按房间价格" />
        </label>
        <label>入住日期<input type="date" name="checkin_date" value="${dateInput(today)}" required /></label>
        <label>预计离店<input type="date" name="planned_checkout_date" value="${dateInput(tomorrow)}" required /></label>
        <label>押金<input type="number" name="deposit" min="0" step="0.01" value="300" /></label>
        <div class="form-actions"><button class="primary-btn" type="submit">办理入住</button></div>
      </form>
      <div class="panel">
        <div class="panel-head"><h3>可用房间</h3></div>
        <div class="room-grid">
          ${rooms.filter((room) => room.status !== "maintenance").slice(0, 6).map(roomCardMini).join("") || `<div class="empty">暂无可用房间</div>`}
        </div>
      </div>
    </section>
  `;
}

async function renderStays() {
  const [stays, settlements] = await Promise.all([api("/api/stays?status=active"), api("/api/settlements")]);
  state.stays = stays;
  $("#content").innerHTML = `
    <section class="split-grid">
      <div class="panel">
        <div class="panel-head"><h3>在住结算台</h3></div>
        ${activeStayTable(stays, true)}
      </div>
      <div class="panel">
        <form id="extraForm" class="form-grid">
          <h3 class="full">登记额外消费</h3>
          <label class="full">入住单<select name="stay_id" required>${stayOptions(stays)}</select></label>
          <label>类别<select name="category">${categoryOptions()}</select></label>
          <label>金额<input name="amount" type="number" min="0.01" step="0.01" required /></label>
          <label class="full">项目<input name="item_name" placeholder="餐饮、洗衣、赔偿等明细" required /></label>
          <div class="form-actions"><button class="secondary-btn" type="submit">登记消费</button></div>
        </form>
        <hr />
        <form id="checkoutForm" class="form-grid">
          <h3 class="full">退房结算</h3>
          <label class="full">入住单<select name="stay_id" required>${stayOptions(stays)}</select></label>
          <label>退房日期<input name="checkout_date" type="date" value="${dateInput(new Date())}" required /></label>
          <label>支付方式<select name="payment_method">${paymentOptions()}</select></label>
          <label>优惠金额<input name="discount" type="number" min="0" step="0.01" value="0" /></label>
          <div class="form-actions"><button class="primary-btn" type="submit">生成结算单</button></div>
        </form>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>结算记录</h3></div>
      ${settlementTable(settlements)}
    </section>
  `;
}

async function renderCustomers(keyword = "") {
  const params = keyword ? `?keyword=${encodeURIComponent(keyword)}` : "";
  state.customers = await api(`/api/customers${params}`);
  $("#content").innerHTML = `
    <section class="panel">
      <form id="customerFilter" class="toolbar">
        <div class="toolbar-group">
          <input name="keyword" placeholder="姓名 / 电话 / 身份证" value="${escapeAttr(keyword)}" />
          <button class="secondary-btn" type="submit">查询</button>
        </div>
        <button class="primary-btn" data-action="open-customer-modal" type="button">新增客户</button>
      </form>
    </section>
    <section class="panel">${customerTable(state.customers)}</section>
  `;
}

async function renderReports() {
  const data = await api("/api/reports");
  const maxRevenue = Math.max(...data.revenue_trend.map((item) => item.total_revenue), 1);
  const maxSource = Math.max(...data.source_stats.map((item) => item.customer_count), 1);
  $("#content").innerHTML = `
    <section class="split-grid">
      <div class="panel">
        <div class="panel-head"><h3>近 14 日收入</h3></div>
        <div class="bar-list">
          ${data.revenue_trend.map((item) => barRow(shortDate(item.date), item.total_revenue, maxRevenue, moneyText(item.total_revenue))).join("")}
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>客户来源</h3></div>
        <div class="bar-list">
          ${data.source_stats.map((item) => barRow(sourceMap[item.source] || item.source, item.customer_count, maxSource, `${item.customer_count} 人`)).join("")}
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>房型入住率</h3></div>
      ${roomTypeTable(data.room_type_stats)}
    </section>
    <section class="panel">
      <div class="panel-head"><h3>月收入汇总</h3></div>
      ${monthlyTable(data.monthly)}
    </section>
  `;
}

async function renderAudit() {
  const logs = await api("/api/audit-logs");
  $("#content").innerHTML = `
    <section class="panel">
      <div class="panel-head"><h3>最近操作</h3></div>
      ${auditTable(logs)}
    </section>
  `;
}

async function handleActionClick(event) {
  const jump = event.target.closest("[data-view-jump]");
  if (jump) {
    await setView(jump.dataset.viewJump);
    return;
  }

  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;

  try {
    if (action === "open-room-modal") openRoomModal();
    if (action === "edit-room") openRoomModal(state.rooms.find((room) => String(room.id) === button.dataset.id));
    if (action === "set-room-status") await setRoomStatus(button.dataset.id, button.dataset.status);
    if (action === "cancel-reservation") await cancelReservation(button.dataset.id);
    if (action === "reservation-checkin") await checkinFromReservation(button.dataset.id);
    if (action === "checkout-stay") openCheckoutModal(button.dataset.id);
    if (action === "open-customer-modal") openCustomerModal();
    if (action === "edit-customer") openCustomerModal(state.customers.find((customer) => String(customer.id) === button.dataset.id));
    if (action === "print-receipt") window.print();
  } catch (error) {
    toast(error.message, true);
  }
}

async function handleFormSubmit(event) {
  const form = event.target;
  if (!form.id) return;
  event.preventDefault();

  try {
    if (form.id === "roomFilter") {
      await renderRooms(serialize(form));
      return;
    }
    if (form.id === "customerFilter") {
      await renderCustomers(serialize(form).keyword || "");
      return;
    }
    if (form.id === "roomForm") {
      await saveRoom(form);
      return;
    }
    if (form.id === "customerForm") {
      await saveCustomer(form);
      return;
    }
    if (form.id === "reservationForm") {
      await saveReservation(form);
      return;
    }
    if (form.id === "checkinForm") {
      await saveCheckin(form);
      return;
    }
    if (form.id === "extraForm") {
      await saveExtra(form);
      return;
    }
    if (form.id === "checkoutForm" || form.id === "checkoutModalForm") {
      await saveCheckout(form);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveRoom(form) {
  const data = serialize(form);
  const id = data.id;
  delete data.id;
  data.floor = Number(data.floor);
  data.bed_count = Number(data.bed_count || 1);
  data.price = Number(data.price);
  if (id) await api(`/api/rooms/${id}`, { method: "PUT", body: data });
  else await api("/api/rooms", { method: "POST", body: data });
  closeModal();
  await renderRooms();
  toast("客房信息已保存");
}

async function saveCustomer(form) {
  const data = serialize(form);
  const id = data.id;
  delete data.id;
  validateCustomerData(data);
  if (id) await api(`/api/customers/${id}`, { method: "PUT", body: data });
  else await api("/api/customers", { method: "POST", body: data });
  closeModal();
  await renderCustomers();
  toast("客户档案已保存");
}

async function saveReservation(form) {
  const data = serialize(form);
  const customer = customerPayload(data);
  validateCustomerData(customer);
  const payload = {
    room_id: Number(data.room_id),
    checkin_date: data.checkin_date,
    checkout_date: data.checkout_date,
    deposit: Number(data.deposit || 0),
    channel: data.channel,
    notes: data.notes,
    customer,
  };
  await api("/api/reservations", { method: "POST", body: payload });
  await renderReservations();
  toast("预订已创建");
}

async function saveCheckin(form) {
  const data = serialize(form);
  const customer = customerPayload(data);
  validateCustomerData(customer);
  const payload = {
    room_id: Number(data.room_id),
    checkin_date: data.checkin_date,
    planned_checkout_date: data.planned_checkout_date,
    room_rate: data.room_rate ? Number(data.room_rate) : undefined,
    deposit: Number(data.deposit || 0),
    customer,
  };
  await api("/api/checkins", { method: "POST", body: payload });
  await renderCheckins();
  toast("入住登记已完成");
}

async function saveExtra(form) {
  const data = serialize(form);
  await api("/api/extras", {
    method: "POST",
    body: {
      stay_id: Number(data.stay_id),
      category: data.category,
      item_name: data.item_name,
      amount: Number(data.amount),
    },
  });
  await renderStays();
  toast("额外消费已登记");
}

async function saveCheckout(form) {
  const data = serialize(form);
  const result = await api("/api/checkouts", {
    method: "POST",
    body: {
      stay_id: Number(data.stay_id),
      checkout_date: data.checkout_date,
      payment_method: data.payment_method,
      discount: Number(data.discount || 0),
    },
  });
  openReceipt(result);
  await renderStays();
  toast("结算单已生成");
}

async function setRoomStatus(id, status) {
  const room = state.rooms.find((item) => String(item.id) === String(id));
  if (!room) return;
  await api(`/api/rooms/${id}`, {
    method: "PUT",
    body: { ...room, status },
  });
  await renderRooms();
  toast("房态已更新");
}

async function cancelReservation(id) {
  if (!confirm("确认取消该预订？")) return;
  await api(`/api/reservations/${id}/cancel`, { method: "PUT", body: {} });
  await renderReservations();
  toast("预订已取消");
}

async function checkinFromReservation(id) {
  await api("/api/checkins", { method: "POST", body: { reservation_id: Number(id) } });
  await renderReservations();
  toast("已按预订办理入住");
}

function openRoomModal(room = {}) {
  showModal(`
    <form id="roomForm" class="form-grid">
      <h3 class="full">${room.id ? "编辑客房" : "新增客房"}</h3>
      <input type="hidden" name="id" value="${escapeAttr(room.id || "")}" />
      <label>房号<input name="room_number" value="${escapeAttr(room.room_number || "")}" required /></label>
      <label>楼层<input name="floor" type="number" min="1" max="99" value="${escapeAttr(room.floor || 1)}" required /></label>
      <label>房型<input name="room_type" value="${escapeAttr(room.room_type || "")}" required /></label>
      <label>床位数<input name="bed_count" type="number" min="1" max="6" value="${escapeAttr(room.bed_count || 1)}" required /></label>
      <label>房价<input name="price" type="number" min="1" step="0.01" value="${escapeAttr(room.price || "")}" required /></label>
      <label>状态<select name="status">
        ${option("free", "空闲", room.status || "free")}
        ${option("reserved", "预订", room.status)}
        ${option("occupied", "入住", room.status)}
        ${option("maintenance", "维修", room.status)}
      </select></label>
      <label class="full">描述<textarea name="description">${escapeHtml(room.description || "")}</textarea></label>
      <div class="form-actions">
        <button class="secondary-btn" type="button" onclick="document.querySelector('#modalClose').click()">取消</button>
        <button class="primary-btn" type="submit">保存</button>
      </div>
    </form>
  `);
}

function openCustomerModal(customer = {}) {
  showModal(`
    <form id="customerForm" class="form-grid">
      <h3 class="full">${customer.id ? "编辑客户" : "新增客户"}</h3>
      <input type="hidden" name="id" value="${escapeAttr(customer.id || "")}" />
      ${customerFields(customer)}
      <label class="full">备注<textarea name="notes">${escapeHtml(customer.notes || "")}</textarea></label>
      <div class="form-actions">
        <button class="secondary-btn" type="button" onclick="document.querySelector('#modalClose').click()">取消</button>
        <button class="primary-btn" type="submit">保存</button>
      </div>
    </form>
  `);
}

function openCheckoutModal(stayId) {
  const stay = state.stays.find((item) => String(item.id) === String(stayId));
  showModal(`
    <form id="checkoutModalForm" class="form-grid">
      <h3 class="full">退房结算</h3>
      <input type="hidden" name="stay_id" value="${escapeAttr(stayId)}" />
      <p class="full">${stay ? `${escapeHtml(stay.customer_name)} · ${escapeHtml(stay.room_number)} · ${escapeHtml(stay.stay_no)}` : ""}</p>
      <label>退房日期<input name="checkout_date" type="date" value="${dateInput(new Date())}" required /></label>
      <label>支付方式<select name="payment_method">${paymentOptions()}</select></label>
      <label>优惠金额<input name="discount" type="number" min="0" step="0.01" value="0" /></label>
      <div class="form-actions">
        <button class="secondary-btn" type="button" onclick="document.querySelector('#modalClose').click()">取消</button>
        <button class="primary-btn" type="submit">生成结算单</button>
      </div>
    </form>
  `);
}

function openReceipt(result) {
  const bill = result.bill;
  const note = result.overdue_days > 0 ? `超时 ${result.overdue_days} 天，已按实际夜数计费` : result.early_checkout ? "提前退房，已按实际夜数计费" : "正常退房";
  showModal(`
    <article class="receipt">
      <div class="receipt-head">
        <div>
          <p class="eyebrow">Settlement Bill</p>
          <h3>酒店退房结算单</h3>
        </div>
        <strong>${escapeHtml(bill.bill_no)}</strong>
      </div>
      <div class="receipt-lines">
        ${receiptLine("客户", result.customer_name)}
        ${receiptLine("房号", result.room_number)}
        ${receiptLine("退房日期", bill.checkout_date)}
        ${receiptLine("住宿夜数", `${bill.nights} 晚`)}
        ${receiptLine("房费", moneyText(bill.room_total))}
        ${receiptLine("额外消费", moneyText(bill.extra_total))}
        ${receiptLine("优惠", moneyText(bill.discount))}
        ${receiptLine("支付方式", paymentMap[bill.payment_method] || bill.payment_method)}
        ${receiptLine("异常处理", note)}
      </div>
      <p class="receipt-total">应收合计：${moneyText(bill.payable_total)}</p>
      <div class="form-actions receipt-actions">
        <button class="secondary-btn" type="button" onclick="document.querySelector('#modalClose').click()">关闭</button>
        <button class="primary-btn" data-action="print-receipt" type="button">打印</button>
      </div>
    </article>
  `);
}

function kpi(label, value, hint) {
  return `<div class="kpi-card"><span>${label}</span><strong>${value}</strong><small>${hint}</small></div>`;
}

function statusBar(label, value, total, color) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return `
    <div class="bar-row">
      <strong>${label}</strong>
      <span class="bar-track"><span class="bar-fill" style="width:${percent}%;background:${color}"></span></span>
      <span>${value} 间</span>
    </div>
  `;
}

function barRow(label, value, max, valueText) {
  const percent = Math.max(4, Math.round((Number(value || 0) / max) * 100));
  return `
    <div class="bar-row">
      <strong>${escapeHtml(label)}</strong>
      <span class="bar-track"><span class="bar-fill" style="width:${percent}%"></span></span>
      <span>${escapeHtml(valueText)}</span>
    </div>
  `;
}

function activeStayTable(rows, withActions = false) {
  if (!rows.length) return `<div class="empty">暂无在住客人</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>入住单</th><th>客户</th><th>房间</th><th>日期</th><th>消费</th>${withActions ? "<th>操作</th>" : ""}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.stay_no)}</td>
              <td>${escapeHtml(row.customer_name)}<br><small>${escapeHtml(row.phone || "")}</small></td>
              <td>${escapeHtml(row.room_number)}<br><small>${escapeHtml(row.room_type || "")}</small></td>
              <td>${escapeHtml(row.checkin_date)}<br><small>至 ${escapeHtml(row.planned_checkout_date)}</small></td>
              <td>${moneyText(row.extra_total || 0)}</td>
              ${withActions ? `<td><button class="table-btn" data-action="checkout-stay" data-id="${row.id}" type="button">结算</button></td>` : ""}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function recentBillTable(rows) {
  if (!rows.length) return `<div class="empty">暂无结算记录</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>账单号</th><th>客户</th><th>房间</th><th>金额</th><th>时间</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.bill_no)}</td>
              <td>${escapeHtml(row.customer_name)}</td>
              <td>${escapeHtml(row.room_number)}</td>
              <td>${moneyText(row.payable_total)}</td>
              <td>${escapeHtml(row.paid_at)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function roomCard(room) {
  const status = statusMap[room.status] || room.status;
  const canMaintain = room.status !== "maintenance";
  return `
    <article class="room-card ${escapeAttr(room.status)}">
      <div class="room-title">
        <div><strong>${escapeHtml(room.room_number)}</strong><span>${escapeHtml(room.room_type)}</span></div>
        ${statusBadge(room.status, status)}
      </div>
      <div class="room-meta">
        <span>${room.floor} 层 · ${room.bed_count} 床 · ${moneyText(room.price)}/晚</span>
        <span>${room.current_guest ? `住客：${escapeHtml(room.current_guest)}` : escapeHtml(room.description || "待客状态良好")}</span>
        <span>未完成预订：${room.future_reservations || 0}</span>
      </div>
      <div class="room-actions">
        <button class="table-btn" data-action="edit-room" data-id="${room.id}" type="button">编辑</button>
        ${canMaintain ? `<button class="table-btn" data-action="set-room-status" data-id="${room.id}" data-status="maintenance" type="button">维修</button>` : `<button class="table-btn" data-action="set-room-status" data-id="${room.id}" data-status="free" type="button">恢复</button>`}
      </div>
    </article>
  `;
}

function roomCardMini(room) {
  return `
    <article class="room-card ${escapeAttr(room.status)}">
      <div class="room-title">
        <div><strong>${escapeHtml(room.room_number)}</strong><span>${escapeHtml(room.room_type)}</span></div>
        ${statusBadge(room.status, statusMap[room.status] || room.status)}
      </div>
      <div class="room-meta">
        <span>${moneyText(room.price)}/晚 · ${room.bed_count} 床</span>
        <span>${escapeHtml(room.description || "")}</span>
      </div>
    </article>
  `;
}

function reservationTable(rows) {
  if (!rows.length) return `<div class="empty">暂无预订记录</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>预订单</th><th>客户</th><th>房间</th><th>日期</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.reservation_no)}</td>
              <td>${escapeHtml(row.customer_name)}<br><small>${escapeHtml(row.phone)}</small></td>
              <td>${escapeHtml(row.room_number)}<br><small>${escapeHtml(row.room_type)}</small></td>
              <td>${escapeHtml(row.checkin_date)}<br><small>至 ${escapeHtml(row.checkout_date)}</small></td>
              <td>${reservationStatusMap[row.status] || row.status}</td>
              <td>
                <div class="row-actions">
                  ${["pending", "confirmed"].includes(row.status) ? `<button class="table-btn" data-action="reservation-checkin" data-id="${row.id}" type="button">入住</button><button class="table-btn" data-action="cancel-reservation" data-id="${row.id}" type="button">取消</button>` : "-"}
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function settlementTable(rows) {
  if (!rows.length) return `<div class="empty">暂无结算记录</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>账单号</th><th>客户</th><th>房间</th><th>夜数</th><th>金额</th><th>支付</th><th>时间</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.bill_no)}</td>
              <td>${escapeHtml(row.customer_name)}<br><small>${escapeHtml(row.phone || "")}</small></td>
              <td>${escapeHtml(row.room_number)}<br><small>${escapeHtml(row.room_type || "")}</small></td>
              <td>${row.nights} 晚<br><small>超时 ${row.overdue_days} 天</small></td>
              <td>${moneyText(row.payable_total)}<br><small>房费 ${moneyText(row.room_total)} / 消费 ${moneyText(row.extra_total)}</small></td>
              <td>${paymentMap[row.payment_method] || row.payment_method}</td>
              <td>${escapeHtml(row.paid_at)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function customerTable(rows) {
  if (!rows.length) return `<div class="empty">暂无客户档案</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>姓名</th><th>身份证</th><th>电话</th><th>来源</th><th>入住历史</th><th>消费合计</th><th>操作</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.name)}</td>
              <td>${escapeHtml(row.id_card)}</td>
              <td>${escapeHtml(row.phone)}</td>
              <td>${sourceMap[row.source] || row.source}</td>
              <td>${row.stay_count || 0} 次<br><small>${row.last_checkout_date || "暂无退房记录"}</small></td>
              <td>${moneyText(row.total_spent || 0)}</td>
              <td><button class="table-btn" data-action="edit-customer" data-id="${row.id}" type="button">编辑</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function roomTypeTable(rows) {
  if (!rows.length) return `<div class="empty">暂无房型数据</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>房型</th><th>总数</th><th>入住</th><th>维修</th><th>入住率</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.room_type)}</td>
              <td>${row.total}</td>
              <td>${row.occupied || 0}</td>
              <td>${row.maintenance || 0}</td>
              <td>${row.occupancy_rate || 0}%</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function monthlyTable(rows) {
  if (!rows.length) return `<div class="empty">暂无月度收入</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>月份</th><th>账单数</th><th>收入</th></tr></thead>
        <tbody>
          ${rows.map((row) => `<tr><td>${escapeHtml(row.month)}</td><td>${row.bill_count}</td><td>${moneyText(row.revenue)}</td></tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function auditTable(rows) {
  if (!rows.length) return `<div class="empty">暂无审计日志</div>`;
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>时间</th><th>人员</th><th>动作</th><th>对象</th><th>详情</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.created_at)}</td>
              <td>${escapeHtml(row.actor_name || "-")}<br><small>${roleMap[row.actor_role] || ""}</small></td>
              <td>${escapeHtml(row.action)}</td>
              <td>${escapeHtml(row.entity)} #${row.entity_id || "-"}</td>
              <td>${escapeHtml(row.detail || "")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function customerFields(values = {}) {
  return `
    <label>姓名<input name="name" value="${escapeAttr(values.name || "")}" minlength="2" maxlength="30" required /></label>
    <label>联系电话<input name="phone" value="${escapeAttr(values.phone || "")}" inputmode="tel" maxlength="18" pattern="(1[3-9][0-9]{9}|0[0-9]{2,3}-?[0-9]{7,8})" title="请输入11位手机号或带区号的固定电话" required /></label>
    <label>身份证号<input name="id_card" value="${escapeAttr(values.id_card || "")}" inputmode="text" maxlength="18" pattern="[1-9][0-9]{5}(18|19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{3}[0-9Xx]" title="请输入18位大陆居民身份证号" required /></label>
    <label>客户来源<select name="source">
      ${Object.entries(sourceMap).map(([value, label]) => option(value, label, values.source || "walk_in")).join("")}
    </select></label>
  `;
}

function customerPayload(data) {
  return {
    name: (data.name || "").trim(),
    phone: normalizePhone(data.phone),
    id_card: normalizeIdCard(data.id_card),
    source: data.source || "walk_in",
    notes: (data.notes || "").trim(),
  };
}

function normalizeIdCard(value) {
  return String(value || "").trim().toUpperCase();
}

function normalizePhone(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function validateCustomerData(data) {
  const name = String(data.name || "").trim();
  if (!/^[\u4e00-\u9fa5A-Za-z·\s]{2,30}$/.test(name)) {
    throw new Error("客户姓名需为2-30个中文、英文或间隔号字符");
  }

  const phone = normalizePhone(data.phone);
  if (!/^(1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$/.test(phone)) {
    throw new Error("联系电话格式不正确，请填写11位手机号或带区号的固定电话");
  }

  const idCard = normalizeIdCard(data.id_card);
  if (!isValidChinaIdCard(idCard)) {
    throw new Error("身份证号格式不正确，请填写真实18位身份证号");
  }

  data.name = name;
  data.phone = phone;
  data.id_card = idCard;
  return data;
}

function isValidChinaIdCard(idCard) {
  if (!/^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$/.test(idCard)) return false;
  const birth = idCard.slice(6, 14);
  const birthDate = new Date(`${birth.slice(0, 4)}-${birth.slice(4, 6)}-${birth.slice(6, 8)}T00:00:00`);
  if (Number.isNaN(birthDate.getTime())) return false;
  if (birthDate.getFullYear() !== Number(birth.slice(0, 4)) || birthDate.getMonth() + 1 !== Number(birth.slice(4, 6)) || birthDate.getDate() !== Number(birth.slice(6, 8))) return false;
  const today = new Date();
  if (birthDate > today) return false;
  let age = today.getFullYear() - birthDate.getFullYear();
  if (today.getMonth() < birthDate.getMonth() || (today.getMonth() === birthDate.getMonth() && today.getDate() < birthDate.getDate())) age -= 1;
  if (age > 120) return false;

  const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
  const codes = "10X98765432";
  const sum = weights.reduce((total, weight, index) => total + Number(idCard[index]) * weight, 0);
  return idCard[17] === codes[sum % 11];
}

function roomOptions(rooms, selected = null, includeReserved = false) {
  const available = rooms.filter((room) => room.status !== "maintenance" && room.status !== "occupied" && (includeReserved || room.status !== "reserved"));
  return available.map((room) => option(room.id, `${room.room_number} · ${room.room_type} · ${moneyText(room.price)}`, selected)).join("");
}

function stayOptions(stays) {
  return stays.map((stay) => option(stay.id, `${stay.room_number} · ${stay.customer_name} · ${stay.stay_no}`)).join("");
}

function categoryOptions() {
  return Object.entries(categoryMap).map(([value, label]) => option(value, label)).join("");
}

function paymentOptions() {
  return Object.entries(paymentMap).map(([value, label]) => option(value, label)).join("");
}

function option(value, label, selected) {
  return `<option value="${escapeAttr(value)}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function statusBadge(status, label) {
  return `<span class="status-badge status-${escapeAttr(status)}">${escapeHtml(label)}</span>`;
}

function receiptLine(label, value) {
  return `<div class="receipt-line"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function serialize(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function showModal(html) {
  $("#modalContent").innerHTML = html;
  $("#modal").classList.remove("is-hidden");
}

function closeModal() {
  $("#modal").classList.add("is-hidden");
  $("#modalContent").innerHTML = "";
}

function toast(message, isError = false) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.toggle("error", isError);
  box.classList.remove("is-hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.add("is-hidden"), 2600);
}

function moneyText(value) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function dateInput(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function shortDate(value) {
  return value.slice(5);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}
