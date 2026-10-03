// Screens import from here. VITE_API=live sends phases 0-5 to the FastAPI backend; otherwise the synthetic
// in-memory mock runs everything (standalone demo). Phase 6/7 features stay on the mock until their endpoints exist.
import * as mock from './mockClient'
import * as live from './live'

export * from './mockClient'

export const LIVE = import.meta.env.VITE_API === 'live'
const pick = <K extends keyof typeof live & keyof typeof mock>(k: K) => (LIVE ? live[k] : mock[k]) as (typeof mock)[K]
const empty = <T,>() => async (): Promise<T[]> => []

export const login = pick('login')
export const verifyTotp = pick('verifyTotp')
export const requestOtp = pick('requestOtp')
export const verifyOtp = pick('verifyOtp')
export const logout = pick('logout')
export const listSites = pick('listSites')
export const stockSummary = pick('stockSummary')
export const listUnits = pick('listUnits')
export const getUnit = pick('getUnit')
export const transitionUnits = pick('transitionUnits')
export const receiveUnit = pick('receiveUnit')
export const importUnits = pick('importUnits')
export const forecast = pick('forecast')
export const listPlans = pick('listPlans')
export const getPlan = pick('getPlan')
export const runPlan = pick('runPlan')
export const decide = pick('decide')
export const listTransfers = pick('listTransfers')
export const previewPick = pick('previewPick')
export const dispatchTransfer = pick('dispatchTransfer')
export const receiveTransfer = pick('receiveTransfer')
export const listUsers = pick('listUsers')
export const updateUser = pick('updateUser')
export const listSettings = pick('listSettings')
export const updateSetting = pick('updateSetting')
export const listCompatRules = pick('listCompatRules')
export const listAudit = pick('listAudit')
export const verifyAudit = pick('verifyAudit')

// Phase 6: requests, donors, matching, low-stock appeals
export const listRequests = pick('listRequests')
export const getRequest = pick('getRequest')
export const createRequest = pick('createRequest')
export const confirmRequest = pick('confirmRequest')
export const cancelRequest = pick('cancelRequest')
export const listRequestMatches = pick('listRequestMatches')
export const recordMatchOutcome = pick('recordMatchOutcome')
export const lowStock = pick('lowStock')
export const createAppeal = pick('createAppeal')
export const listDonors = pick('listDonors')
export const addDeferral = pick('addDeferral')
export const verifyGroup = pick('verifyGroup')
export const getDonorProfile = pick('getDonorProfile')
export const updateDonorProfile = pick('updateDonorProfile')
export const exportDonorData = pick('exportDonorData')
export const deleteDonorData = pick('deleteDonorData')
export const listInvitations = pick('listInvitations')
export const respondInvitation = pick('respondInvitation')
export const getThread = pick('getThread')
export const sendMessage = pick('sendMessage')
export const sharePhone = pick('sharePhone')

// Phase 7 (alerts, reports) still runs on the mock only
export const listAlerts = LIVE ? empty<Awaited<ReturnType<typeof mock.listAlerts>>[number]>() : mock.listAlerts
export const report = LIVE ? (async () => []) as typeof mock.report : mock.report
export const setAlertStatus = LIVE ? (live.notYet as typeof mock.setAlertStatus) : mock.setAlertStatus
