import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api'
import { todayCivilInput } from '../civilDate'
import Modal from './Modal'

interface Conta { id: number; nome: string; dono: string; saldo: number }
interface Cartao { id: number; nome: string; dono: string }
interface Categoria { id: number; nome: string }
interface Meta {
  id: number; nome: string; valor_alvo: number; saldo: number;
  prazo: string | null; progresso_percentual: number;
}
interface Alerta { tipo: string; severidade: string; mensagem: string }
interface PontoProjecao { dias: number; data: string; saldo_projetado: number }
interface Projecao { saldo_atual: number; pontos: PontoProjecao[] }
interface OrcamentoStatus {
  id: number; categoria_id: number; limite: number; gasto: number;
  disponivel: number; percentual: number; situacao: string;
}
interface Recorrencia { id: number; descricao: string; valor: number; proxima_data: string; ativa: boolean }

interface Props {
  apiUrl: string;
  activeProfile: string;
  contas: Conta[];
  cartoes: Cartao[];
  categorias: Categoria[];
}

const formatter = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const money = (valor: number) => formatter.format(valor)
const numberValue = (value: FormDataEntryValue | null) => Number(String(value || '0').replace(',', '.'))

export default function Planejamento({ apiUrl, activeProfile, contas, cartoes, categorias }: Props) {
  const [alertas, setAlertas] = useState<Alerta[]>([])
  const [projecao, setProjecao] = useState<Projecao | null>(null)
  const [metas, setMetas] = useState<Meta[]>([])
  const [orcamentos, setOrcamentos] = useState<OrcamentoStatus[]>([])
  const [recorrencias, setRecorrencias] = useState<Recorrencia[]>([])
  const [metaModal, setMetaModal] = useState(false)
  const [orcamentoModal, setOrcamentoModal] = useState(false)
  const [recorrenciaModal, setRecorrenciaModal] = useState(false)
  const [tipoRecorrencia, setTipoRecorrencia] = useState<'gasto' | 'receita'>('gasto')
  const [pagamentoRecorrencia, setPagamentoRecorrencia] = useState('pix')
  const [activeSection, setActiveSection] = useState<'visao' | 'metas' | 'orcamentos' | 'recorrencias'>('visao')
  const [showAllAlerts, setShowAllAlerts] = useState(false)

  const carregar = useCallback(async () => {
    const hoje = new Date()
    const queryDono = encodeURIComponent(activeProfile)
    const [novosAlertas, novaProjecao, novasMetas, novosOrcamentos, novasRecorrencias] = await Promise.all([
      apiRequest<Alerta[]>(`${apiUrl}/relatorios/alertas?dono=${queryDono}`),
      apiRequest<Projecao>(`${apiUrl}/relatorios/projecao?dias=90&dono=${queryDono}`),
      apiRequest<Meta[]>(`${apiUrl}/planejamento/metas?dono=${queryDono}`),
      apiRequest<OrcamentoStatus[]>(`${apiUrl}/relatorios/orcamentos/status?mes=${hoje.getMonth() + 1}&ano=${hoje.getFullYear()}&dono=${queryDono}`),
      apiRequest<Recorrencia[]>(`${apiUrl}/planejamento/recorrencias`),
    ])
    setAlertas(novosAlertas)
    setProjecao(novaProjecao)
    setMetas(novasMetas)
    setOrcamentos(novosOrcamentos)
    setRecorrencias(novasRecorrencias)
  }, [activeProfile, apiUrl])

  useEffect(() => { carregar().catch(console.error) }, [carregar])

  const salvarMeta = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await apiRequest(`${apiUrl}/planejamento/metas`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nome: form.get('nome'), dono: activeProfile,
        valor_alvo: numberValue(form.get('valor_alvo')),
        prazo: form.get('prazo') || null,
      }),
    })
    setMetaModal(false)
    await carregar()
  }

  const salvarOrcamento = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const hoje = new Date()
    await apiRequest(`${apiUrl}/planejamento/orcamentos`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        categoria_id: Number(form.get('categoria_id')), dono: activeProfile,
        mes: hoje.getMonth() + 1, ano: hoje.getFullYear(),
        limite: numberValue(form.get('limite')), alerta_percentual: 80,
      }),
    })
    setOrcamentoModal(false)
    await carregar()
  }

  const salvarRecorrencia = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const data = String(form.get('proxima_data'))
    const destino = Number(form.get('destino_id'))
    const payload: Record<string, unknown> = {
      tipo_lancamento: tipoRecorrencia,
      descricao: form.get('descricao'), valor: numberValue(form.get('valor')),
      proxima_data: data, dia_mes: Number(data.slice(8, 10)), parcelas: 1,
      categoria_id: form.get('categoria_id') ? Number(form.get('categoria_id')) : null,
    }
    if (tipoRecorrencia === 'receita') payload.conta_id = destino
    else if (pagamentoRecorrencia === 'credito') {
      payload.cartao_id = destino
      payload.tipo_pagamento = 'credito'
    } else {
      payload.conta_id = destino
      payload.tipo_pagamento = pagamentoRecorrencia
    }
    await apiRequest(`${apiUrl}/planejamento/recorrencias`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    setRecorrenciaModal(false)
    await carregar()
  }

  const movimentarMeta = async (meta: Meta, tipo: 'aporte' | 'retirada') => {
    const valor = window.prompt(`Valor para ${tipo === 'aporte' ? 'aportar' : 'retirar'} em ${meta.nome}:`)
    if (!valor) return
    const opcoes = contas.filter(c => c.dono === activeProfile).map(c => `${c.id}: ${c.nome}`).join('\n')
    const contaId = window.prompt(`Informe o ID da conta:\n${opcoes}`)
    if (!contaId) return
    const payload = {
      conta_id: Number(contaId), meta_id: meta.id, valor: numberValue(valor),
      data: todayCivilInput(), descricao: `${tipo === 'aporte' ? 'Aporte' : 'Retirada'} - ${meta.nome}`,
    }
    const url = tipo === 'aporte'
      ? `${apiUrl}/aportes_reserva/`
      : `${apiUrl}/planejamento/metas/${meta.id}/retiradas`
    await apiRequest(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    await carregar()
  }

  return (
    <section className="page-section">
      <div className="section-heading">
        <div><span className="eyebrow">Futuro financeiro</span><h2>Planejamento</h2></div>
      </div>

      <div className="sub-tabs planning-tabs" role="tablist" aria-label="Área de planejamento">
        <button className={activeSection === 'visao' ? 'active' : ''} onClick={() => setActiveSection('visao')}>Visão futura</button>
        <button className={activeSection === 'metas' ? 'active' : ''} onClick={() => setActiveSection('metas')}>Metas</button>
        <button className={activeSection === 'orcamentos' ? 'active' : ''} onClick={() => setActiveSection('orcamentos')}>Orçamentos</button>
        <button className={activeSection === 'recorrencias' ? 'active' : ''} onClick={() => setActiveSection('recorrencias')}>Recorrências</button>
      </div>

      {activeSection === 'visao' && (
        <>
          <div className="metrics-grid planning-metrics">
            <div className="glass-panel metric-card"><span className="metric-label">Saldo atual</span><span className="metric-value">{money(projecao?.saldo_atual || 0)}</span></div>
            {projecao?.pontos.map(ponto => (
              <div key={ponto.dias} className="glass-panel metric-card">
                <span className="metric-label">Em {ponto.dias} dias</span>
                <span className="metric-value">{money(ponto.saldo_projetado)}</span>
              </div>
            ))}
          </div>
          <div className="content-section">
            <div className="content-section-title"><h3>Alertas importantes</h3><span>{alertas.length}</span></div>
            {alertas.length === 0 ? <div className="glass-panel empty-state"><p>Tudo sob controle por aqui.</p></div> : (
              <div className="alerts-list">
                {(showAllAlerts ? alertas : alertas.slice(0, 3)).map((alerta, index) => (
                  <div key={`${alerta.tipo}-${index}`} className={`glass-panel alert-row severity-${alerta.severidade}`}>
                    <strong>{alerta.severidade === 'alta' ? 'Atenção' : 'Aviso'}</strong><span>{alerta.mensagem}</span>
                  </div>
                ))}
                {alertas.length > 3 && <button className="text-button align-start" onClick={() => setShowAllAlerts(value => !value)}>{showAllAlerts ? 'Mostrar menos' : `Ver todos os ${alertas.length} alertas`}</button>}
              </div>
            )}
          </div>
        </>
      )}

      {activeSection === 'metas' && (
        <div className="content-section">
          <div className="content-section-title section-title-actions"><div><h3>Metas financeiras</h3><p>Acompanhe um objetivo de cada vez.</p></div><button className="btn btn-primary" onClick={() => setMetaModal(true)}>+ Nova meta</button></div>
          {metas.length === 0 ? <div className="glass-panel empty-state"><p>Você ainda não criou nenhuma meta.</p></div> : (
            <div className="wallet-grid">
              {metas.map(meta => (
                <div key={meta.id} className="glass-panel goal-card">
                  <div className="flex-between"><strong>{meta.nome}</strong><span>{Math.round(meta.progresso_percentual)}%</span></div>
                  <div className="goal-progress"><span style={{ width: `${Math.min(meta.progresso_percentual, 100)}%` }} /></div>
                  <span className="metric-hint">{money(meta.saldo)} de {money(meta.valor_alvo)}</span>
                  <div className="card-actions"><button className="btn btn-primary" onClick={() => movimentarMeta(meta, 'aporte')}>Aportar</button><button className="btn" onClick={() => movimentarMeta(meta, 'retirada')}>Retirar</button></div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeSection === 'orcamentos' && (
        <div className="content-section">
          <div className="content-section-title section-title-actions"><div><h3>Orçamentos do mês</h3><p>Limites por categoria para manter o ritmo.</p></div><button className="btn btn-primary" onClick={() => setOrcamentoModal(true)}>+ Orçamento</button></div>
          {orcamentos.length === 0 ? <div className="glass-panel empty-state"><p>Nenhum orçamento definido para este mês.</p></div> : (
            <div className="wallet-grid">{orcamentos.map(item => (
              <div key={item.id} className="glass-panel goal-card">
                <div className="flex-between"><strong>{categorias.find(c => c.id === item.categoria_id)?.nome || 'Categoria'}</strong><span>{Math.round(item.percentual)}%</span></div>
                <div className="goal-progress budget"><span style={{ width: `${Math.min(item.percentual, 100)}%` }} /></div>
                <span className="metric-hint">{money(item.gasto)} de {money(item.limite)} · {item.situacao}</span>
              </div>
            ))}</div>
          )}
        </div>
      )}

      {activeSection === 'recorrencias' && (
        <div className="content-section">
          <div className="content-section-title section-title-actions">
            <div><h3>Recorrências</h3><p>Contas e receitas que se repetem.</p></div>
            <div className="compact-actions"><button className="btn" onClick={async () => { await apiRequest(`${apiUrl}/planejamento/recorrencias/processar`, { method: 'POST' }); await carregar() }}>Processar agora</button><button className="btn btn-primary" onClick={() => setRecorrenciaModal(true)}>+ Recorrência</button></div>
          </div>
          <div className="glass-panel recurring-list">
            {recorrencias.length === 0 ? <p>Nenhuma recorrência cadastrada.</p> : recorrencias.map(item => (
              <div key={item.id} className="recurring-row"><div><strong>{item.descricao}</strong><span>Próxima em {item.proxima_data}</span></div><strong>{money(item.valor)}</strong></div>
            ))}
          </div>
        </div>
      )}

      <Modal isOpen={metaModal} onClose={() => setMetaModal(false)} title="Nova meta">
        <form onSubmit={salvarMeta}>
          <div className="form-group"><label>Nome</label><input className="form-input" name="nome" required /></div>
          <div className="form-group"><label>Valor alvo</label><input className="form-input" name="valor_alvo" type="number" min="0.01" step="0.01" required /></div>
          <div className="form-group"><label>Prazo</label><input className="form-input" name="prazo" type="date" /></div>
          <button className="btn btn-primary" type="submit">Salvar meta</button>
        </form>
      </Modal>

      <Modal isOpen={orcamentoModal} onClose={() => setOrcamentoModal(false)} title="Orçamento mensal">
        <form onSubmit={salvarOrcamento}>
          <div className="form-group"><label>Categoria</label><select className="form-select" name="categoria_id" required>{categorias.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
          <div className="form-group"><label>Limite</label><input className="form-input" name="limite" type="number" min="0.01" step="0.01" required /></div>
          <button className="btn btn-primary" type="submit">Salvar orçamento</button>
        </form>
      </Modal>

      <Modal isOpen={recorrenciaModal} onClose={() => setRecorrenciaModal(false)} title="Novo lançamento recorrente">
        <form onSubmit={salvarRecorrencia}>
          <div className="form-group"><label>Tipo</label><select className="form-select" value={tipoRecorrencia} onChange={e => setTipoRecorrencia(e.target.value as 'gasto' | 'receita')}><option value="gasto">Gasto</option><option value="receita">Receita</option></select></div>
          <div className="form-group"><label>Descrição</label><input className="form-input" name="descricao" required /></div>
          <div className="form-group"><label>Valor</label><input className="form-input" name="valor" type="number" min="0.01" step="0.01" required /></div>
          <div className="form-group"><label>Próxima data</label><input className="form-input" name="proxima_data" type="date" defaultValue={todayCivilInput()} required /></div>
          {tipoRecorrencia === 'gasto' && <div className="form-group"><label>Pagamento</label><select className="form-select" value={pagamentoRecorrencia} onChange={e => setPagamentoRecorrencia(e.target.value)}><option value="pix">PIX</option><option value="debito">Débito</option><option value="credito">Crédito</option></select></div>}
          <div className="form-group"><label>{pagamentoRecorrencia === 'credito' && tipoRecorrencia === 'gasto' ? 'Cartão' : 'Conta'}</label><select className="form-select" name="destino_id" required>{(pagamentoRecorrencia === 'credito' && tipoRecorrencia === 'gasto' ? cartoes : contas).filter(item => item.dono === activeProfile).map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}</select></div>
          <div className="form-group"><label>Categoria</label><select className="form-select" name="categoria_id"><option value="">Sem categoria</option>{categorias.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
          <button className="btn btn-primary" type="submit">Salvar recorrência</button>
        </form>
      </Modal>
    </section>
  )
}
