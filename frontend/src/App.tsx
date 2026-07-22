import { useState, useEffect } from 'react'
import GastoForm from './components/GastoForm'
ISTO EH UM ERRO PROPOSITAL PARA ACIONAR O HERMES;
import GastosList from './components/GastosList'

interface Cartao {
  id: number;
  nome: string;
  dono: string;
  limite: number;
  saldo: number;
  data_fatura: number;
  dia_vencimento: number;
  fatura_atual: number;
}

const API_URL = import.meta.env.VITE_API_URL || '/api';

function App() {
  const [activeProfile, setActiveProfile] = useState<'Eu' | 'Vô'>('Eu')
  const [cartoes, setCartoes] = useState<Cartao[]>([])
  const [loading, setLoading] = useState(true)

  // Modal States
  const [isCartaoModalOpen, setIsCartaoModalOpen] = useState(false)
  const [isReceitaModalOpen, setIsReceitaModalOpen] = useState(false)
  const [isGastoModalOpen, setIsGastoModalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<'dashboard' | 'gastos'>('dashboard')

  // Recalcular faturas dinamicamente
  const fetchDados = async () => {
    try {
      const [cartoesRes, gastosRes] = await Promise.all([
        fetch(`${API_URL}/cartoes/`),
        fetch(`${API_URL}/gastos_diarios/`)
      ])
      const cartoesData = await cartoesRes.json()
      const gastosData = await gastosRes.json()
      
      // Motor de cálculo de faturas
      const hoje = new Date()
      const mesAtual = hoje.getMonth()
      const anoAtual = hoje.getFullYear()

      cartoesData.forEach((cartao: any) => {
        const diaFechamento = cartao.data_fatura || 15
        
        let faturaCalculada = 0
        gastosData.forEach((g: any) => {
          if (g.cartao_id === cartao.id && g.tipo_pagamento.toLowerCase() === 'credito' && !g.pago) {
            const d = new Date(g.data)
            let mesFatura = d.getMonth()
            let anoFatura = d.getFullYear()
            
            if (d.getDate() > diaFechamento) {
              mesFatura += 1
              if (mesFatura > 11) {
                mesFatura = 0
                anoFatura += 1
              }
            }
            
            if (mesFatura === mesAtual && anoFatura === anoAtual) {
              faturaCalculada += g.valor
            }
          }
        })
        cartao.fatura_atual = faturaCalculada
      })

      setCartoes(cartoesData)
    } catch (error) {
      console.error("Erro ao buscar dados:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDados()
  }, [])

  // Filtragem e Cálculos
  const cartoesFiltrados = cartoes.filter(c => c.dono === activeProfile)
  const saldoTotal = cartoesFiltrados.reduce((acc, c) => acc + c.saldo, 0)
  const faturaTotal = cartoesFiltrados.reduce((acc, c) => acc + c.fatura_atual, 0)

  const formatMoney = (value: number) => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value)
  }

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
    await fetch(`${API_URL}/cartoes/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    setIsCartaoModalOpen(false)
    fetchDados()
  }

  const handleCriarReceita = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const payload = {
      descricao: formData.get('descricao'),
      valor: parseMoney(formData.get('valor')),
      data: formData.get('data'),
      cartao_id: Number(formData.get('cartao_id'))
    }
    await fetch(`${API_URL}/receitas/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    setIsReceitaModalOpen(false)
    fetchDados()
  }

  const handleCriarGasto = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const payload = {
      descricao: formData.get('descricao'),
      valor: parseMoney(formData.get('valor')),
      data: formData.get('data'),
      tipo_pagamento: formData.get('tipo_pagamento'),
      parcelas: Number(formData.get('parcelas')),
      cartao_id: Number(formData.get('cartao_id'))
    }
    await fetch(`${API_URL}/gastos_diarios/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    setIsGastoModalOpen(false)
    fetchDados()
  }

  const handlePagarFatura = async (cartaoId: number) => {
    if (!confirm("Confirmar pagamento da fatura com o saldo da conta?")) return
    await fetch(`${API_URL}/cartoes/${cartaoId}/pagar_fatura`, { method: 'POST' })
    fetchDados()
  }

  return (
    <div className="container">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem' }}>
        <div>
          <h1 style={{ color: 'var(--accent-primary)' }}>Finanças Pro</h1>
          <p>Visão geral e controle inteligente</p>
        </div>
        
        <div className="glass-panel" style={{ padding: '0.5rem', display: 'flex', gap: '0.5rem' }}>
          <button 
            className={`btn transition-all ${activeProfile === 'Eu' ? 'btn-primary' : ''}`}
            style={{ padding: '0.5rem 1rem', background: activeProfile !== 'Eu' ? 'transparent' : '', color: activeProfile !== 'Eu' ? 'var(--text-secondary)' : '' }}
            onClick={() => setActiveProfile('Eu')}
          >
            Meu Perfil
          </button>
          <button 
            className={`btn transition-all ${activeProfile === 'Vô' ? 'btn-primary' : ''}`}
            style={{ padding: '0.5rem 1rem', background: activeProfile !== 'Vô' ? 'transparent' : '', color: activeProfile !== 'Vô' ? 'var(--text-secondary)' : '' }}
            onClick={() => setActiveProfile('Vô')}
          >
            Perfil do Vô
          </button>
        </div>
      </header>

      {/* Navegação por Abas */}
      <div className="glass-panel nav-tabs">
        <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
          📊 Dashboard
        </button>
        <button className={`nav-tab ${activeTab === 'gastos' ? 'active' : ''}`} onClick={() => setActiveTab('gastos')}>
          📋 Meus Gastos
        </button>
      </div>

      <main>
      {activeTab === 'dashboard' ? (
        <>
        <div className="action-bar">
          <button className="btn btn-primary" onClick={() => setIsReceitaModalOpen(true)}>+ Nova Receita</button>
          <button className="btn transition-all" style={{ background: 'var(--danger)', color: 'white' }} onClick={() => setIsGastoModalOpen(true)}>- Novo Gasto</button>
          <button className="btn transition-all" style={{ background: 'var(--bg-surface-hover)', color: 'white' }} onClick={() => setIsCartaoModalOpen(true)}>Adicionar Conta/Cartão</button>
        </div>

        {/* Resumo Financeiro */}
        <div className="dashboard-grid">
          <div className="glass-panel summary-box hover-lift transition-all">
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Saldo Disponível</span>
            <span className="summary-value" style={{ color: 'var(--success)' }}>{formatMoney(saldoTotal)}</span>
          </div>
          
          <div className="glass-panel summary-box hover-lift transition-all">
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Faturas em Aberto</span>
            <span className="summary-value" style={{ color: 'var(--danger)' }}>{formatMoney(faturaTotal)}</span>
          </div>
        </div>

        {/* Lista de Cartões */}
        <h2 style={{ marginBottom: '1.5rem' }}>Minhas Contas e Cartões</h2>
        
        {loading ? (
          <p>Carregando dados...</p>
        ) : cartoesFiltrados.length === 0 ? (
          <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <p>Nenhum cartão encontrado para este perfil.</p>
          </div>
        ) : (
          <div className="dashboard-grid">
            {cartoesFiltrados.map(cartao => (
              <div key={cartao.id} className="glass-panel card-item hover-lift transition-all">
                <div className="card-header">
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>{cartao.nome}</h3>
                  <span style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem', borderRadius: 'var(--radius-full)', background: 'rgba(99, 102, 241, 0.2)', color: 'var(--accent-primary)' }}>
                    Vence dia {cartao.dia_vencimento}
                  </span>
                </div>
                
                <div className="card-body">
                  <div className="flex-between">
                    <span style={{ color: 'var(--text-secondary)' }}>Saldo na Conta</span>
                    <span style={{ fontWeight: 600, color: 'var(--success)' }}>{formatMoney(cartao.saldo)}</span>
                  </div>
                  <div className="flex-between">
                    <span style={{ color: 'var(--text-secondary)' }}>Fatura Atual</span>
                    <span style={{ fontWeight: 600, color: 'var(--danger)' }}>{formatMoney(cartao.fatura_atual)}</span>
                  </div>
                  <div className="flex-between">
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Limite Disponível</span>
                    <span style={{ fontWeight: 500, fontSize: '0.85rem' }}>{formatMoney(cartao.limite)}</span>
                  </div>
                </div>
                
                <button 
                  className="btn transition-all" 
                  style={{ marginTop: '0.5rem', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)', color: 'white' }}
                  onClick={() => handlePagarFatura(cartao.id)}
                >
                  Pagar Fatura
                </button>
              </div>
            ))}
          </div>
        )}
        </>
      ) : (
        <GastosList apiUrl={API_URL} activeProfile={activeProfile} />
      )}
      </main>

      {/* MODAIS */}
      
      {/* Modal Novo Cartão */}
      <Modal isOpen={isCartaoModalOpen} onClose={() => setIsCartaoModalOpen(false)} title="Adicionar Nova Conta/Cartão">
        <form onSubmit={handleCriarCartao}>
          <div className="form-group">
            <label>Nome do Banco/Cartão</label>
            <input name="nome" type="text" className="form-input" placeholder="Ex: Nubank" required />
          </div>
          <div className="form-group">
            <label>Limite Total de Crédito</label>
            <input name="limite" type="number" className="form-input" placeholder="Ex: 5000" required />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }}>Salvar Conta</button>
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
            <input name="valor" type="number" step="0.01" className="form-input" placeholder="Ex: 3500" required />
          </div>
          <div className="form-group">
            <label>Data de Recebimento</label>
            <input name="data" type="date" className="form-input" defaultValue={new Date().toISOString().split('T')[0]} required />
          </div>
          <div className="form-group">
            <label>Em qual conta entrou?</label>
            <select name="cartao_id" className="form-select" required>
              <option value="">Selecione a conta...</option>
              {cartoesFiltrados.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
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
            <input name="valor" type="number" step="0.01" className="form-input" placeholder="Ex: 1000" required />
          </div>
          <div className="form-group">
            <label>Data da Compra</label>
            <input name="data" type="date" className="form-input" defaultValue={new Date().toISOString().split('T')[0]} required />
          </div>
          <div className="form-group">
            <label>Forma de Pagamento</label>
            <select name="tipo_pagamento" className="form-select" required>
              <option value="credito">Crédito</option>
              <option value="debito">Débito</option>
              <option value="pix">PIX</option>
            </select>
          </div>
          <div className="form-group">
            <label>Quantidade de Parcelas</label>
            <input name="parcelas" type="number" defaultValue="1" min="1" className="form-input" required />
          </div>
          <div className="form-group">
            <label>Qual Cartão/Conta?</label>
            <select name="cartao_id" className="form-select" required>
              <option value="">Selecione a conta...</option>
              {cartoesFiltrados.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem', background: 'var(--danger)' }}>Registrar Gasto</button>
        </form>
      </Modal>

    </div>
  )
}

export default App
