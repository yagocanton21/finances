import { useState, useEffect, useCallback } from 'react'
import Modal from './components/Modal'
import GastosList from './components/GastosList'
import Planejamento from './components/Planejamento'
import { apiRequest } from './api'
import { todayCivilInput } from './civilDate'

interface Cartao {
  id: number;
  nome: string;
  dono: string;
  limite: number;
  saldo: number;
  data_fatura: number;
  dia_vencimento: number;
  fatura_atual: number;
  limite_total: number;
  conta_padrao_id: number;
}

interface Conta {
  id: number;
  nome: string;
  dono: string;
  saldo: number;
}

interface Categoria {
  id: number;
  nome: string;
}

interface ResumoMensal {
  guardado: number;
  categorias: { nome: string; total: number }[];
  regime: { competencia: number; caixa: number };
  saldo_disponivel_atual: number;
}

interface PagamentoFatura {
  id: number; valor: number; data_pagamento: string; situacao: string;
  origem: string; conta_id: number | null; estornado_em: string | null;
}

interface FaturaDetalhe {
  id?: number; mes_ref: number; ano_ref: number; total: number;
  total_pago: number; saldo_restante: number; situacao: string;
  pagamentos: PagamentoFatura[];
}

type PrimaryTab = 'dashboard' | 'movimentacoes' | 'carteira' | 'planejamento'
type MovementView = 'diarios' | 'parcelas'
type QuickAction = 'receita' | 'gasto' | 'aporte' | 'transferencia' | 'conta' | 'cartao'

const API_URL = import.meta.env.VITE_API_URL || '/api';

// Formatter criado uma única vez no nível de módulo (evita recriação a cada render)
const moneyFormatter = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const formatMoney = (value: number) => moneyFormatter.format(value);

function App() {
  const [activeProfile, setActiveProfile] = useState<'Eu' | 'Vô'>('Eu')
  const [cartoes, setCartoes] = useState<Cartao[]>([])
  const [contas, setContas] = useState<Conta[]>([])
  const [categorias, setCategorias] = useState<Categoria[]>([])
  const [resumoMensal, setResumoMensal] = useState<ResumoMensal | null>(null)
  const [loading, setLoading] = useState(true)

  // Modal States
  const [isCartaoModalOpen, setIsCartaoModalOpen] = useState(false)
  const [isContaModalOpen, setIsContaModalOpen] = useState(false)
  const [isReceitaModalOpen, setIsReceitaModalOpen] = useState(false)
  const [isGastoModalOpen, setIsGastoModalOpen] = useState(false)
  const [isAporteModalOpen, setIsAporteModalOpen] = useState(false)
  const [isTransferenciaModalOpen, setIsTransferenciaModalOpen] = useState(false)
  const [isQuickActionsOpen, setIsQuickActionsOpen] = useState(false)
  const [cartaoPagamento, setCartaoPagamento] = useState<Cartao | null>(null)
  const [faturaDetalhe, setFaturaDetalhe] = useState<{ cartao: Cartao; fatura: FaturaDetalhe } | null>(null)
  const [tipoPagamentoGasto, setTipoPagamentoGasto] = useState<'credito' | 'debito' | 'pix'>('credito')
  const [activeTab, setActiveTab] = useState<PrimaryTab>('dashboard')
  const [movementView, setMovementView] = useState<MovementView>('diarios')

  // Recalcular faturas dinamicamente
  const fetchDados = async () => {
    try {
      const [cartoesData, contasData, categoriasData] = await Promise.all([
        apiRequest<Cartao[]>(`${API_URL}/cartoes/`),
        apiRequest<Conta[]>(`${API_URL}/contas/`),
        apiRequest<Categoria[]>(`${API_URL}/categorias/`),
      ])
      setCartoes(cartoesData)
      setContas(contasData)
      setCategorias(categoriasData)
    } catch (error) {
      console.error("Erro ao buscar dados:", error)
    } finally {
      setLoading(false)
    }
  }

  const fetchResumo = useCallback(async () => {
    const agora = new Date()
    const resumo = await apiRequest<ResumoMensal>(
      `${API_URL}/relatorios/resumo_mensal?mes=${agora.getMonth() + 1}&ano=${agora.getFullYear()}&dono=${encodeURIComponent(activeProfile)}`
    )
    setResumoMensal(resumo)
  }, [activeProfile])

  useEffect(() => {
    fetchDados()
  }, [])

  useEffect(() => {
    fetchResumo().catch(error => console.error('Erro ao buscar resumo mensal:', error))
  }, [fetchResumo])

  // Filtragem e Cálculos
  const cartoesFiltrados = cartoes.filter(c => c.dono === activeProfile)
  const contasFiltradas = contas.filter(c => c.dono === activeProfile)
  const saldoTotal = contasFiltradas.reduce((acc, c) => acc + c.saldo, 0)
  const faturaTotal = cartoesFiltrados.reduce((acc, c) => acc + c.fatura_atual, 0)


  const parseMoney = (value: FormDataEntryValue | null) => {
    if (!value) return 0;
    return parseFloat(value.toString().replace(',', '.'));
  }

  // Ações da API
  const handleCriarCartao = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const payload = {
      nome: formData.get('nome'),
      limite: parseMoney(formData.get('limite')),
      dono: activeProfile,
      saldo: 0,
      data_fatura: 15,
      dia_vencimento: 20,
      fatura_atual: 0
    }
    try {
      await apiRequest(`${API_URL}/cartoes/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      setIsCartaoModalOpen(false)
      await fetchDados()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao criar conta')
    }
  }

  const handleCriarConta = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    try {
      await apiRequest(`${API_URL}/contas/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nome: formData.get('nome'), dono: activeProfile,
          tipo: formData.get('tipo'), saldo: parseMoney(formData.get('saldo')),
        }),
      })
      setIsContaModalOpen(false)
      await fetchDados()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao criar conta')
    }
  }

  const handleCriarReceita = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const payload = {
      descricao: formData.get('descricao'),
      valor: parseMoney(formData.get('valor')),
      data: formData.get('data'),
      categoria_id: formData.get('categoria_id') ? Number(formData.get('categoria_id')) : null,
      conta_id: Number(formData.get('conta_id'))
    }
    try {
      await apiRequest(`${API_URL}/receitas/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      setIsReceitaModalOpen(false)
      await fetchDados()
      await fetchResumo()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao criar receita')
    }
  }

  const handleCriarGasto = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const tipoPagamento = formData.get('tipo_pagamento') as 'credito' | 'debito' | 'pix'
    const destinoId = Number(formData.get('destino_id'))
    const payload = {
      descricao: formData.get('descricao'),
      valor: parseMoney(formData.get('valor')),
      data: formData.get('data'),
      tipo_pagamento: tipoPagamento,
      parcelas: Number(formData.get('parcelas')),
      categoria_id: formData.get('categoria_id') ? Number(formData.get('categoria_id')) : null,
      cartao_id: tipoPagamento === 'credito' ? destinoId : null,
      conta_id: tipoPagamento === 'credito' ? null : destinoId,
    }
    try {
      await apiRequest(`${API_URL}/gastos_diarios/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      setIsGastoModalOpen(false)
      await fetchDados()
      await fetchResumo()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao criar gasto')
    }
  }

  const handlePagarFatura = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!cartaoPagamento) return
    const form = new FormData(e.currentTarget)
    try {
      await apiRequest(`${API_URL}/cartoes/${cartaoPagamento.id}/pagar_fatura`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conta_id: Number(form.get('conta_id')),
          idempotency_key: crypto.randomUUID(),
        }),
      })
      setCartaoPagamento(null)
      await fetchDados()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao pagar fatura')
    }
  }

  const handleAbrirFatura = async (cartao: Cartao) => {
    try {
      const fatura = await apiRequest<FaturaDetalhe>(`${API_URL}/cartoes/${cartao.id}/fatura`)
      setFaturaDetalhe({ cartao, fatura })
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao consultar fatura')
    }
  }

  const handleEstornarPagamento = async (pagamentoId: number) => {
    if (!faturaDetalhe || !confirm('Estornar este pagamento e reabrir a fatura?')) return
    try {
      await apiRequest(`${API_URL}/cartoes/${faturaDetalhe.cartao.id}/pagamentos/${pagamentoId}/estornar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo: 'Estorno solicitado pelo frontend', idempotency_key: crypto.randomUUID() }),
      })
      await fetchDados()
      await handleAbrirFatura(faturaDetalhe.cartao)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao estornar pagamento')
    }
  }

  const handleTransferir = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    try {
      await apiRequest(`${API_URL}/contas/transferencias`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conta_origem_id: Number(form.get('conta_origem_id')),
          conta_destino_id: Number(form.get('conta_destino_id')),
          descricao: form.get('descricao'), valor: parseMoney(form.get('valor')),
          data: form.get('data'), idempotency_key: crypto.randomUUID(),
        }),
      })
      setIsTransferenciaModalOpen(false)
      await fetchDados()
      await fetchResumo()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao transferir')
    }
  }

  const handleCriarAporte = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const payload = {
      descricao: formData.get('descricao'),
      valor: parseMoney(formData.get('valor')),
      data: formData.get('data'),
      conta_id: Number(formData.get('conta_id')),
    }
    try {
      await apiRequest(`${API_URL}/aportes_reserva/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setIsAporteModalOpen(false)
      await fetchDados()
      await fetchResumo()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao guardar valor')
    }
  }

  const abrirAcao = (acao: QuickAction) => {
    setIsQuickActionsOpen(false)
    if (acao === 'receita') setIsReceitaModalOpen(true)
    if (acao === 'gasto') setIsGastoModalOpen(true)
    if (acao === 'aporte') setIsAporteModalOpen(true)
    if (acao === 'transferencia') setIsTransferenciaModalOpen(true)
    if (acao === 'conta') setIsContaModalOpen(true)
    if (acao === 'cartao') setIsCartaoModalOpen(true)
  }

  return (
    <div className="container">
      <header className="app-header">
        <div className="brand-block">
          <span className="brand-kicker">Controle financeiro</span>
          <h1>Finanças Pro</h1>
          <p>O essencial primeiro. Os detalhes quando você precisar.</p>
        </div>

        <div className="header-actions">
          <div className="profile-switcher" aria-label="Selecionar perfil">
          <button
            className={`profile-option ${activeProfile === 'Eu' ? 'active' : ''}`}
            onClick={() => setActiveProfile('Eu')}
          >
            Eu
          </button>
          <button
            className={`profile-option ${activeProfile === 'Vô' ? 'active' : ''}`}
            onClick={() => setActiveProfile('Vô')}
          >
            Vô
          </button>
          </div>
          <button className="btn btn-primary quick-action-trigger" onClick={() => setIsQuickActionsOpen(true)}>
            <span aria-hidden="true">+</span> Nova movimentação
          </button>
        </div>
      </header>

      <nav className="glass-panel nav-tabs" aria-label="Navegação principal">
        <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
          Início
        </button>
        <button className={`nav-tab ${activeTab === 'movimentacoes' ? 'active' : ''}`} onClick={() => setActiveTab('movimentacoes')}>
          Movimentações
        </button>
        <button className={`nav-tab ${activeTab === 'carteira' ? 'active' : ''}`} onClick={() => setActiveTab('carteira')}>
          Contas e cartões
        </button>
        <button className={`nav-tab ${activeTab === 'planejamento' ? 'active' : ''}`} onClick={() => setActiveTab('planejamento')}>
          Planejamento
        </button>
      </nav>

      <main>
        {activeTab === 'dashboard' ? (
          <section className="page-section">
            <div className="section-heading">
              <div><span className="eyebrow">Visão geral</span><h2>Seu mês em poucos números</h2></div>
              <span className="context-chip">Perfil: {activeProfile}</span>
            </div>

            <div className="metrics-grid">
              <div className="glass-panel metric-card metric-positive">
                <span className="metric-label">Saldo disponível</span>
                <span className="metric-value">{formatMoney(saldoTotal)}</span>
                <span className="metric-hint">Em {contasFiltradas.length} {contasFiltradas.length === 1 ? 'conta' : 'contas'}</span>
              </div>
              <div className="glass-panel metric-card metric-negative">
                <span className="metric-label">Faturas em aberto</span>
                <span className="metric-value">{formatMoney(faturaTotal)}</span>
                <span className="metric-hint">Em {cartoesFiltrados.length} {cartoesFiltrados.length === 1 ? 'cartão' : 'cartões'}</span>
              </div>
              <div className="glass-panel metric-card">
                <span className="metric-label">Guardado no mês</span>
                <span className="metric-value">{formatMoney(resumoMensal?.guardado || 0)}</span>
                <span className="metric-hint">Reserva acumulada no período</span>
              </div>
              <div className="glass-panel metric-card">
                <span className="metric-label">Resultado de caixa</span>
                <span className="metric-value">{formatMoney(resumoMensal?.regime.caixa || 0)}</span>
                <span className="metric-hint">Entradas menos saídas efetivas</span>
              </div>
            </div>

            <div className="overview-grid">
              <div className="glass-panel focus-panel">
                <div className="panel-heading">
                  <div><span className="eyebrow">Onde mais gastou</span><h3>Principais categorias</h3></div>
                  <button className="text-button" onClick={() => setActiveTab('movimentacoes')}>Ver movimentações</button>
                </div>
                {!resumoMensal || resumoMensal.categorias.length === 0 ? <p>Nenhum gasto categorizado neste mês.</p> : resumoMensal.categorias.slice(0, 3).map((item, index) => (
                  <div key={item.nome} className="rank-row"><span className="rank-number">{index + 1}</span><span>{item.nome}</span><strong>{formatMoney(item.total)}</strong></div>
                ))}
              </div>
              <div className="glass-panel focus-panel">
                <div className="panel-heading">
                  <div><span className="eyebrow">Sua estrutura</span><h3>Contas e cartões</h3></div>
                  <button className="text-button" onClick={() => setActiveTab('carteira')}>Gerenciar</button>
                </div>
                <div className="wallet-summary-row"><span>Contas ativas</span><strong>{contasFiltradas.length}</strong></div>
                <div className="wallet-summary-row"><span>Cartões ativos</span><strong>{cartoesFiltrados.length}</strong></div>
                <div className="wallet-summary-row"><span>Limite disponível</span><strong>{formatMoney(cartoesFiltrados.reduce((total, cartao) => total + cartao.limite, 0))}</strong></div>
              </div>
            </div>
          </section>
        ) : activeTab === 'movimentacoes' ? (
          <section className="page-section">
            <div className="section-heading">
              <div><span className="eyebrow">Histórico</span><h2>Movimentações</h2></div>
              <button className="btn btn-primary" onClick={() => setIsQuickActionsOpen(true)}>+ Adicionar</button>
            </div>
            <div className="sub-tabs" role="tablist" aria-label="Tipo de movimentação">
              <button className={movementView === 'diarios' ? 'active' : ''} onClick={() => setMovementView('diarios')}>Gastos do mês</button>
              <button className={movementView === 'parcelas' ? 'active' : ''} onClick={() => setMovementView('parcelas')}>Compras parceladas</button>
            </div>
            <GastosList apiUrl={API_URL} activeProfile={activeProfile} categorias={categorias} contas={contas} viewMode={movementView} />
          </section>
        ) : activeTab === 'carteira' ? (
          <section className="page-section">
            <div className="section-heading">
              <div><span className="eyebrow">Carteira</span><h2>Contas e cartões</h2></div>
              <div className="compact-actions">
                <button className="btn" onClick={() => abrirAcao('transferencia')}>Transferir</button>
                <button className="btn" onClick={() => abrirAcao('conta')}>+ Conta</button>
                <button className="btn btn-primary" onClick={() => abrirAcao('cartao')}>+ Cartão</button>
              </div>
            </div>

            <div className="content-section">
              <div className="content-section-title"><h3>Contas</h3><span>{contasFiltradas.length}</span></div>
              {contasFiltradas.length === 0 ? <div className="glass-panel empty-state"><p>Nenhuma conta cadastrada para este perfil.</p></div> : (
                <div className="wallet-grid">
                  {contasFiltradas.map(conta => (
                    <article key={conta.id} className="glass-panel wallet-card">
                      <span className="wallet-card-type">Conta</span><h3>{conta.nome}</h3>
                      <span className="wallet-card-label">Saldo disponível</span><strong className="wallet-card-value">{formatMoney(conta.saldo)}</strong>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <div className="content-section">
              <div className="content-section-title"><h3>Cartões</h3><span>{cartoesFiltrados.length}</span></div>
              {loading ? <p>Carregando dados...</p> : cartoesFiltrados.length === 0 ? <div className="glass-panel empty-state"><p>Nenhum cartão cadastrado para este perfil.</p></div> : (
                <div className="wallet-grid">
                  {cartoesFiltrados.map(cartao => (
                    <article key={cartao.id} className="glass-panel wallet-card credit-card">
                      <div className="card-header">
                        <div><span className="wallet-card-type">Cartão</span><h3>{cartao.nome}</h3></div>
                        <span className="due-chip">Vence dia {cartao.dia_vencimento}</span>
                      </div>
                      <div className="wallet-card-stats">
                        <div><span>Fatura atual</span><strong className="danger-text">{formatMoney(cartao.fatura_atual)}</strong></div>
                        <div><span>Limite disponível</span><strong>{formatMoney(cartao.limite)}</strong></div>
                      </div>
                      <div className="card-actions">
                        <button className="btn btn-primary" onClick={() => setCartaoPagamento(cartao)}>Pagar fatura</button>
                        <button className="btn" onClick={() => handleAbrirFatura(cartao)}>Detalhes</button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        ) : activeTab === 'planejamento' ? (
          <Planejamento apiUrl={API_URL} activeProfile={activeProfile} contas={contas} cartoes={cartoes} categorias={categorias} />
        ) : null}
      </main>

      {/* MODAIS */}

      <Modal isOpen={isQuickActionsOpen} onClose={() => setIsQuickActionsOpen(false)} title="Nova movimentação">
        <p className="modal-intro">O que você quer registrar?</p>
        <div className="quick-action-grid">
          <button className="quick-action-card income" onClick={() => abrirAcao('receita')}><strong>Receita</strong><span>Dinheiro que entrou</span></button>
          <button className="quick-action-card expense" onClick={() => abrirAcao('gasto')}><strong>Gasto</strong><span>Compra ou pagamento</span></button>
          <button className="quick-action-card" onClick={() => abrirAcao('transferencia')}><strong>Transferência</strong><span>Entre suas contas</span></button>
          <button className="quick-action-card" onClick={() => abrirAcao('aporte')}><strong>Guardar dinheiro</strong><span>Separar para uma meta</span></button>
        </div>
        <div className="modal-secondary-actions">
          <span>Configurar carteira</span>
          <button className="text-button" onClick={() => abrirAcao('conta')}>Adicionar conta</button>
          <button className="text-button" onClick={() => abrirAcao('cartao')}>Adicionar cartão</button>
        </div>
      </Modal>

      {/* Modal Novo Cartão */}
      <Modal isOpen={isCartaoModalOpen} onClose={() => setIsCartaoModalOpen(false)} title="Adicionar Nova Conta/Cartão">
        <form onSubmit={handleCriarCartao}>
          <div className="form-group">
            <label>Nome do Banco/Cartão</label>
            <input name="nome" type="text" className="form-input" placeholder="Ex: Nubank" required />
          </div>
          <div className="form-group">
            <label>Limite Total de Crédito</label>
            <input name="limite" type="number" min="0" step="0.01" className="form-input" placeholder="Ex: 5000" required />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }}>Salvar Conta</button>
        </form>
      </Modal>

      <Modal isOpen={isContaModalOpen} onClose={() => setIsContaModalOpen(false)} title="Adicionar Nova Conta">
        <form onSubmit={handleCriarConta}>
          <div className="form-group"><label>Nome da conta</label><input name="nome" className="form-input" placeholder="Ex: Conta Itaú" required /></div>
          <div className="form-group"><label>Tipo</label><select name="tipo" className="form-select"><option value="corrente">Corrente</option><option value="poupanca">Poupança</option><option value="dinheiro">Dinheiro</option><option value="investimento">Investimento</option></select></div>
          <div className="form-group"><label>Saldo inicial</label><input name="saldo" type="number" step="0.01" className="form-input" defaultValue="0" required /></div>
          <button type="submit" className="btn btn-primary">Salvar conta</button>
        </form>
      </Modal>

      {/* Modal Nova Receita */}
      <Modal isOpen={isReceitaModalOpen} onClose={() => setIsReceitaModalOpen(false)} title="Registrar Receita (Entrada)">
        <form onSubmit={handleCriarReceita}>
          <div className="form-group">
            <label>Descrição</label>
            <input name="descricao" type="text" className="form-input" placeholder="Ex: Salário" required />
          </div>
          <div className="form-group">
            <label>Valor (R$)</label>
            <input name="valor" type="number" min="0.01" step="0.01" className="form-input" placeholder="Ex: 3500" required />
          </div>
          <div className="form-group">
            <label>Data de Recebimento</label>
            <input name="data" type="date" className="form-input" defaultValue={todayCivilInput()} required />
          </div>
          <div className="form-group">
            <label>Em qual conta entrou?</label>
            <select name="conta_id" className="form-select" required>
              <option value="">Selecione a conta...</option>
              {contasFiltradas.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Categoria</label>
            <select name="categoria_id" className="form-select">
              <option value="">Sem categoria</option>
              {categorias.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }}>Salvar Receita</button>
        </form>
      </Modal>

      {/* Modal Novo Gasto */}
      <Modal isOpen={isGastoModalOpen} onClose={() => setIsGastoModalOpen(false)} title="Registrar Gasto (Saída)">
        <form onSubmit={handleCriarGasto}>
          <div className="form-group">
            <label>Descrição</label>
            <input name="descricao" type="text" className="form-input" placeholder="Ex: Geladeira Nova" required />
          </div>
          <div className="form-group">
            <label>Valor Total (R$)</label>
            <input name="valor" type="number" min="0.01" step="0.01" className="form-input" placeholder="Ex: 1000" required />
          </div>
          <div className="form-group">
            <label>Data da Compra</label>
            <input name="data" type="date" className="form-input" defaultValue={todayCivilInput()} required />
          </div>
          <div className="form-group">
            <label>Forma de Pagamento</label>
            <select name="tipo_pagamento" className="form-select" value={tipoPagamentoGasto} onChange={e => setTipoPagamentoGasto(e.target.value as 'credito' | 'debito' | 'pix')} required>
              <option value="credito">Crédito</option>
              <option value="debito">Débito</option>
              <option value="pix">PIX</option>
            </select>
          </div>
          <div className="form-group">
            <label>Quantidade de Parcelas</label>
            <input name="parcelas" type="number" defaultValue="1" min="1" max="120" className="form-input" required />
          </div>
          <div className="form-group">
            <label>{tipoPagamentoGasto === 'credito' ? 'Qual cartão?' : 'Qual conta?'}</label>
            <select name="destino_id" className="form-select" required>
              <option value="">Selecione...</option>
              {(tipoPagamentoGasto === 'credito' ? cartoesFiltrados : contasFiltradas).map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Categoria</label>
            <select name="categoria_id" className="form-select">
              <option value="">Sem categoria</option>
              {categorias.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem', background: 'var(--danger)' }}>Registrar Gasto</button>
        </form>
      </Modal>

      <Modal isOpen={isAporteModalOpen} onClose={() => setIsAporteModalOpen(false)} title="Guardar Dinheiro">
        <form onSubmit={handleCriarAporte}>
          <div className="form-group">
            <label>Descrição</label>
            <input name="descricao" type="text" className="form-input" defaultValue="Reserva mensal" required />
          </div>
          <div className="form-group">
            <label>Valor guardado (R$)</label>
            <input name="valor" type="number" min="0.01" step="0.01" className="form-input" required />
          </div>
          <div className="form-group">
            <label>Data</label>
            <input name="data" type="date" className="form-input" defaultValue={todayCivilInput()} required />
          </div>
          <div className="form-group">
            <label>Retirar de qual conta?</label>
            <select name="conta_id" className="form-select" required>
              <option value="">Selecione a conta...</option>
              {contasFiltradas.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem', background: 'var(--success)' }}>Guardar valor</button>
        </form>
      </Modal>

      <Modal isOpen={isTransferenciaModalOpen} onClose={() => setIsTransferenciaModalOpen(false)} title="Transferir entre contas">
        <form onSubmit={handleTransferir}>
          <div className="form-group"><label>Conta de origem</label><select name="conta_origem_id" className="form-select" required><option value="">Selecione...</option>{contasFiltradas.map(c => <option key={c.id} value={c.id}>{c.nome} — {formatMoney(c.saldo)}</option>)}</select></div>
          <div className="form-group"><label>Conta de destino</label><select name="conta_destino_id" className="form-select" required><option value="">Selecione...</option>{contasFiltradas.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
          <div className="form-group"><label>Descrição</label><input name="descricao" className="form-input" defaultValue="Transferência entre contas" required /></div>
          <div className="form-group"><label>Valor</label><input name="valor" type="number" min="0.01" step="0.01" className="form-input" required /></div>
          <div className="form-group"><label>Data</label><input name="data" type="date" className="form-input" defaultValue={todayCivilInput()} required /></div>
          <button type="submit" className="btn btn-primary">Transferir</button>
        </form>
      </Modal>

      <Modal isOpen={!!cartaoPagamento} onClose={() => setCartaoPagamento(null)} title="Pagar fatura">
        <form onSubmit={handlePagarFatura}>
          <p>Cartão: <strong>{cartaoPagamento?.nome}</strong></p>
          <div className="form-group">
            <label>Debitar de qual conta?</label>
            <select name="conta_id" className="form-select" defaultValue={cartaoPagamento?.conta_padrao_id} required>
              {contasFiltradas.map(c => <option key={c.id} value={c.id}>{c.nome} — {formatMoney(c.saldo)}</option>)}
            </select>
          </div>
          <button type="submit" className="btn btn-primary">Confirmar pagamento</button>
        </form>
      </Modal>

      <Modal isOpen={!!faturaDetalhe} onClose={() => setFaturaDetalhe(null)} title="Detalhes da fatura">
        {faturaDetalhe && (
          <div>
            <div className="flex-between"><span>Competência</span><strong>{String(faturaDetalhe.fatura.mes_ref).padStart(2, '0')}/{faturaDetalhe.fatura.ano_ref}</strong></div>
            <div className="flex-between"><span>Total</span><strong>{formatMoney(faturaDetalhe.fatura.total)}</strong></div>
            <div className="flex-between"><span>Pago</span><strong>{formatMoney(faturaDetalhe.fatura.total_pago)}</strong></div>
            <div className="flex-between"><span>Restante</span><strong>{formatMoney(faturaDetalhe.fatura.saldo_restante)}</strong></div>
            <h3>Pagamentos</h3>
            {faturaDetalhe.fatura.pagamentos.length === 0 ? <p>Nenhum pagamento registrado.</p> : faturaDetalhe.fatura.pagamentos.map(item => (
              <div key={item.id} className="flex-between">
                <span>{formatMoney(item.valor)} · {item.origem} · {item.situacao}</span>
                {!item.estornado_em && <button className="btn" onClick={() => handleEstornarPagamento(item.id)}>Estornar</button>}
              </div>
            ))}
          </div>
        )}
      </Modal>

    </div>
  )
}

export default App
